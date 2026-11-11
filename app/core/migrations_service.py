"""Servicio de diagnostico, aprovisionamiento y ejecucion de migraciones/DDL en Oracle XE 21c."""
from __future__ import annotations

import datetime as dt
import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import oracledb
import pandas as pd

from app.config import BASE_DIR
from app.core.connection import DatabaseConnectionManager, db_manager


BASE_TABLES_21 = (
    "USUARIO_SISTEMA",
    "PROPIETARIO",
    "CLIENTE",
    "MUNICIPIO",
    "TIPO_ALOJAMIENTO",
    "ALOJAMIENTO",
    "TIPO_HABITACION",
    "HABITACION",
    "COMODIDAD",
    "ALOJAMIENTO_COMODIDAD",
    "TEMPORADA",
    "TARIFA",
    "AUDITORIA_TARIFA",
    "RESERVA",
    "RESERVA_HABITACION",
    "PAGO",
    "SERVICIO",
    "RESERVA_SERVICIO",
    "RESENA",
    "LIQUIDACION_MENSUAL",
    "HISTORICO_RESERVA",
)

MODEL_TABLES_22 = BASE_TABLES_21 + ("RESERVA_HABITACION_TARIFA_APLICADA",)

ANALYTIC_VIEWS = (
    "VW_CALENDARIO_MES",
    "VW_INGRESO_RESERVA",
    "VW_INGRESO_HOSPEDAJE_TEMPORADA",
    "VW_OCUPACION_MENSUAL_BASE",
)

E2_OBJECTS = (
    "PKG_TURISMOUQ",
    "TRG_AUDITAR_TARIFA",
    "TRG_RESERVA_HABITACION",
    "TRG_RESERVA",
)

E3_VIEWS = (
    "V_E3_ALOJAMIENTOS",
    "V_E3_HABITACIONES",
    "V_E3_CLIENTES",
    "V_E3_TARIFAS_COTIZACION",
    "V_E3_SOLICITUD_PAGO",
    "V_E3_ADMIN_TARIFAS",
    "V_E3_GERENCIA_MENSUAL",
    "V_E3_AUDITORIA_TARIFA",
)

E3_INDEXES = (
    "IX_E3_RESERVA_ALOJ_CHECKIN",
    "IX_E3_PAGO_DIA",
    "IX_E3_RESERVA_ESTADO_CHECKOUT",
)

REQUIRED_OWNER_PRIVS = (
    "CREATE SESSION",
    "CREATE TABLE",
    "CREATE VIEW",
    "CREATE MATERIALIZED VIEW",
    "CREATE SEQUENCE",
    "CREATE PROCEDURE",
    "CREATE TRIGGER",
)


@dataclass
class ExecutionStepResult:
    label: str
    script_path: str
    success: bool
    elapsed_ms: float
    statements_executed: int = 0
    output_lines: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


def _strip_leading_comments(text: str) -> str:
    """Elimina comentarios iniciales (-- y /* */) para identificar el primer token SQL."""
    s = text.lstrip()
    while s:
        if s.startswith("--"):
            newline = s.find("\n")
            if newline == -1:
                return ""
            s = s[newline + 1 :].lstrip()
        elif s.startswith("/*"):
            end_comment = s.find("*/")
            if end_comment == -1:
                return ""
            s = s[end_comment + 2 :].lstrip()
        else:
            break
    return s


def _is_plsql_or_slash_block(text: str) -> bool:
    """Determina si el bloque requiere terminador '/' en lugar de ';'."""
    cleaned = _strip_leading_comments(text)
    if not cleaned:
        return False
    if re.match(r"^(DECLARE|BEGIN)\b", cleaned, flags=re.IGNORECASE):
        return True
    if re.match(
        r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:EDITIONABLE\s+|NONEDITIONABLE\s+)?(?:PACKAGE|PROCEDURE|FUNCTION|TRIGGER|TYPE)\b",
        cleaned,
        flags=re.IGNORECASE,
    ):
        return True
    return False


class SqlScriptSession:
    """Ejecutor nativo en Python (oracledb) compatible con scripts SQL*Plus del proyecto."""

    def __init__(
        self,
        connection: oracledb.Connection,
        base_dir: Path = BASE_DIR,
        initial_defines: Optional[Dict[str, str]] = None,
    ):
        self.connection = connection
        self.base_dir = base_dir
        self.define_enabled = True
        self.defines: Dict[str, str] = {
            k.upper(): str(v) for k, v in (initial_defines or {}).items()
        }
        self.new_value_cols: Dict[str, str] = {}
        self.session_vars: Dict[str, oracledb.Var] = {}
        self.output_lines: List[str] = []
        self.statements_executed: int = 0

    def enable_dbms_output(self, cursor: oracledb.Cursor) -> None:
        try:
            cursor.callproc("DBMS_OUTPUT.ENABLE", [None])
        except Exception:
            pass

    def flush_dbms_output(self, cursor: oracledb.Cursor) -> None:
        try:
            lines_var = cursor.arrayvar(str, 100)
            num_lines_var = cursor.var(int)
            while True:
                num_lines_var.setvalue(0, 100)
                cursor.callproc("DBMS_OUTPUT.GET_LINES", (lines_var, num_lines_var))
                count = num_lines_var.getvalue()
                if not count:
                    break
                for line in lines_var.getvalue()[:count]:
                    if line is not None:
                        self.output_lines.append(line)
        except Exception:
            pass

    def _substitute_defines(self, text: str) -> str:
        if not self.define_enabled or "&" not in text:
            return text

        def repl(match: re.Match) -> str:
            var_name = match.group(1).upper()
            if var_name in self.defines:
                return self.defines[var_name]
            return match.group(0)

        return re.sub(r"&&?([A-Za-z0-9_]+)\.?", repl, text)

    def _allocate_variable(self, cursor: oracledb.Cursor, name: str, type_spec: str) -> None:
        spec_upper = type_spec.upper().strip()
        if spec_upper.startswith("NUMBER"):
            self.session_vars[name.lower()] = cursor.var(oracledb.DB_TYPE_NUMBER)
        else:
            m = re.search(r"\((\d+)\)", spec_upper)
            size = int(m.group(1)) if m else 4000
            self.session_vars[name.lower()] = cursor.var(oracledb.DB_TYPE_VARCHAR, size=size)

    def _execute_single_statement(
        self, cursor: oracledb.Cursor, raw_stmt: str, is_plsql: bool
    ) -> None:
        stmt = self._substitute_defines(raw_stmt).strip()
        if not stmt:
            return
        if not is_plsql:
            # Eliminar comentarios al final y el punto y coma de cierre en sentencias SQL
            stmt = re.sub(r"(?m)\s*--[^\n]*$", "", stmt).strip()
            if stmt.endswith(";"):
                stmt = stmt[:-1].strip()
        if not stmt or not _strip_leading_comments(stmt):
            return

        upper_clean = _strip_leading_comments(stmt).upper()
        if upper_clean == "COMMIT":
            self.connection.commit()
            self.statements_executed += 1
            return
        if upper_clean == "ROLLBACK":
            self.connection.rollback()
            self.statements_executed += 1
            return

        # Identificar variables de sesion (:carga_semilla, :carga_referencia, etc.) usadas
        binds = {}
        if self.session_vars:
            used_names = {
                m.group(1).lower()
                for m in re.finditer(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)", stmt)
                if m.group(1).upper() not in ("NEW", "OLD")
            }
            for var_name in used_names:
                if var_name in self.session_vars:
                    binds[var_name] = self.session_vars[var_name]

        if binds:
            cursor.execute(stmt, binds)
        else:
            cursor.execute(stmt)

        self.statements_executed += 1

        if cursor.description is not None:
            cols = [c[0].upper() for c in cursor.description]
            rows = cursor.fetchall()
            for row in rows:
                for col_name, val in zip(cols, row):
                    if col_name in self.new_value_cols and val is not None:
                        self.defines[self.new_value_cols[col_name]] = str(val)

        self.flush_dbms_output(cursor)

    def execute_file(
        self,
        script_path: Path,
        args: Optional[List[str]] = None,
        override_defines: Optional[Dict[str, str]] = None,
    ) -> None:
        if not script_path.exists():
            raise FileNotFoundError(f"No se encontró el script: {script_path}")

        if args:
            for idx, arg_val in enumerate(args, start=1):
                self.defines[str(idx)] = arg_val

        text = script_path.read_text(encoding="utf-8-sig")
        self.execute_script_text(text, current_dir=script_path.parent, override_defines=override_defines)

    def execute_script_text(
        self,
        text: str,
        current_dir: Optional[Path] = None,
        override_defines: Optional[Dict[str, str]] = None,
    ) -> None:
        current_dir = current_dir or self.base_dir
        override_keys = {k.upper(): str(v) for k, v in (override_defines or {}).items()}
        self.defines.update(override_keys)

        with self.connection.cursor() as cursor:
            self.enable_dbms_output(cursor)
            buffer: List[str] = []
            in_plsql_mode = False
            in_block_comment = False

            for raw_line in text.splitlines():
                stripped = raw_line.strip()

                # Si el buffer está vacío, evaluar comentarios y directivas SQL*Plus
                if not buffer:
                    if in_block_comment:
                        if "*/" in stripped:
                            in_block_comment = False
                        continue
                    if not stripped or stripped.startswith("--") or stripped.upper().startswith("REM "):
                        continue
                    if stripped.startswith("/*"):
                        if "*/" not in stripped:
                            in_block_comment = True
                        continue

                    # Directivas SQL*Plus
                    m_set = re.match(r"^SET\s+(.*)$", stripped, flags=re.IGNORECASE)
                    if m_set:
                        rest = m_set.group(1).upper()
                        if "DEFINE OFF" in rest:
                            self.define_enabled = False
                        elif "DEFINE ON" in rest:
                            self.define_enabled = True
                        continue

                    if re.match(r"^(WHENEVER|SPOOL|SHOW)\b", stripped, flags=re.IGNORECASE):
                        continue

                    if re.match(r"^EXIT\b", stripped, flags=re.IGNORECASE):
                        break

                    m_prompt = re.match(r"^PROMPT\s*(.*)$", stripped, flags=re.IGNORECASE)
                    if m_prompt:
                        self.output_lines.append(m_prompt.group(1))
                        continue

                    m_def = re.match(
                        r"^DEFINE\s+([A-Za-z0-9_]+)\s*=\s*(.+)$", stripped, flags=re.IGNORECASE
                    )
                    if m_def:
                        var_name = m_def.group(1).upper()
                        var_val = m_def.group(2).strip()
                        if (var_val.startswith('"') and var_val.endswith('"')) or (
                            var_val.startswith("'") and var_val.endswith("'")
                        ):
                            var_val = var_val[1:-1]
                        if var_name in override_keys:
                            self.defines[var_name] = override_keys[var_name]
                        else:
                            self.defines[var_name] = var_val
                        continue

                    m_undef = re.match(r"^UNDEFINE\s+([A-Za-z0-9_]+)\s*$", stripped, flags=re.IGNORECASE)
                    if m_undef:
                        self.defines.pop(m_undef.group(1).upper(), None)
                        continue

                    m_col = re.match(
                        r"^COLUMN\s+([A-Za-z0-9_]+)\s+NEW_VALUE\s+([A-Za-z0-9_]+)",
                        stripped,
                        flags=re.IGNORECASE,
                    )
                    if m_col:
                        self.new_value_cols[m_col.group(1).upper()] = m_col.group(2).upper()
                        continue

                    if re.match(r"^COLUMN\b", stripped, flags=re.IGNORECASE):
                        continue

                    m_var = re.match(
                        r"^VARIABLE\s+([A-Za-z0-9_]+)\s+(.+)$", stripped, flags=re.IGNORECASE
                    )
                    if m_var:
                        self._allocate_variable(cursor, m_var.group(1), m_var.group(2))
                        continue

                    if stripped.startswith("@@") or stripped.startswith("@"):
                        inc_cmd = stripped[2:].strip() if stripped.startswith("@@") else stripped[1:].strip()
                        parts = shlex.split(inc_cmd)
                        inc_rel = parts[0]
                        inc_args = parts[1:]
                        inc_path = (self.base_dir / inc_rel).resolve()
                        if not inc_path.exists():
                            inc_path = (current_dir / inc_rel).resolve()
                        self.execute_file(inc_path, args=inc_args, override_defines=override_defines)
                        continue

                    # Inicio de sentencia SQL o bloque PL/SQL
                    buffer.append(raw_line)
                    in_plsql_mode = _is_plsql_or_slash_block("\n".join(buffer))

                    if not in_plsql_mode:
                        # Verificar si termina en ';' en la misma línea
                        line_no_comment = re.sub(r"--.*$", "", raw_line).strip()
                        if line_no_comment.endswith(";"):
                            self._execute_single_statement(cursor, "\n".join(buffer), is_plsql=False)
                            buffer.clear()
                else:
                    # Estamos dentro de una sentencia multilínea
                    if stripped == "/":
                        self._execute_single_statement(cursor, "\n".join(buffer), is_plsql=in_plsql_mode)
                        buffer.clear()
                        in_plsql_mode = False
                        continue

                    buffer.append(raw_line)
                    if not in_plsql_mode:
                        in_plsql_mode = _is_plsql_or_slash_block("\n".join(buffer))

                    if not in_plsql_mode:
                        line_no_comment = re.sub(r"--.*$", "", raw_line).strip()
                        if line_no_comment.endswith(";"):
                            self._execute_single_statement(cursor, "\n".join(buffer), is_plsql=False)
                            buffer.clear()

            # Si quedó algo pendiente en el buffer al final del archivo
            if buffer:
                remaining = "\n".join(buffer).strip()
                if remaining and _strip_leading_comments(remaining):
                    self._execute_single_statement(cursor, remaining, is_plsql=in_plsql_mode)
                buffer.clear()


class MigrationsService:
    """Servicio de diagnostico e instalacion de DDL, carga y migraciones para TurismoUQ."""

    def __init__(self, database: DatabaseConnectionManager = db_manager):
        self.database = database

    def get_schema_status(self) -> Dict[str, Any]:
        """Inspecciona el esquema conectado para diagnosticar el estado de las Entregas 1, 2 y 3."""
        status: Dict[str, Any] = {
            "connected_user": "",
            "current_schema": "",
            "container": "",
            "is_admin": False,
            "tablespace_ready": False,
            "direct_privs": [],
            "session_privs": [],
            "missing_direct_privs": [],
            "tables_present": [],
            "tables_22_count": 0,
            "has_tramos_table": False,
            "has_solicitud_pago_table": False,
            "table_row_counts": {},
            "data_loaded": False,
            "analytic_views_valid": [],
            "mv_status": None,
            "e2_migration_ready": False,
            "e2_objects_valid": [],
            "e2_triggers_enabled": [],
            "e3_objects_valid": [],
            "e3_indexes_present": [],
            "invalid_objects": [],
            "user_errors": [],
        }

        with self.database.get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT SYS_CONTEXT('USERENV', 'SESSION_USER'), "
                "SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA'), "
                "SYS_CONTEXT('USERENV', 'CON_NAME') FROM dual"
            )
            user, schema, con_name = cur.fetchone()
            status["connected_user"] = user
            status["current_schema"] = schema
            status["container"] = con_name
            status["is_admin"] = user in ("SYS", "SYSTEM")

            # Tablespace TS_HISTORICO_RESERVAS
            cur.execute(
                "SELECT COUNT(*) FROM user_tablespaces WHERE tablespace_name = 'TS_HISTORICO_RESERVAS'"
            )
            status["tablespace_ready"] = cur.fetchone()[0] == 1

            # Privilegios directos (USER_SYS_PRIVS) y de sesion (SESSION_PRIVS)
            cur.execute("SELECT privilege FROM user_sys_privs ORDER BY privilege")
            direct_privs = {r[0] for r in cur.fetchall()}
            status["direct_privs"] = sorted(direct_privs)

            cur.execute("SELECT privilege FROM session_privs ORDER BY privilege")
            session_privs = {r[0] for r in cur.fetchall()}
            status["session_privs"] = sorted(session_privs)

            status["missing_direct_privs"] = [
                p for p in ("CREATE PROCEDURE", "CREATE TRIGGER", "CREATE MATERIALIZED VIEW", "CREATE VIEW", "CREATE TABLE", "CREATE SEQUENCE")
                if p not in direct_privs and (p in ("CREATE PROCEDURE", "CREATE TRIGGER") or p not in session_privs)
            ]

            # Tablas del usuario
            cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
            user_tables = {r[0] for r in cur.fetchall()}
            status["tables_present"] = sorted(user_tables)
            status["tables_22_count"] = sum(1 for t in MODEL_TABLES_22 if t in user_tables)
            status["has_tramos_table"] = "RESERVA_HABITACION_TARIFA_APLICADA" in user_tables
            status["has_solicitud_pago_table"] = "SOLICITUD_PAGO" in user_tables

            # Conteo de filas en tablas clave si existen
            key_tables = ("MUNICIPIO", "ALOJAMIENTO", "HABITACION", "CLIENTE", "RESERVA", "RESERVA_SERVICIO", "PAGO")
            counts = {}
            for tbl in key_tables:
                if tbl in user_tables:
                    cur.execute(f'SELECT COUNT(*) FROM "{tbl}"')
                    counts[tbl] = int(cur.fetchone()[0])
            status["table_row_counts"] = counts
            status["data_loaded"] = counts.get("RESERVA", 0) >= 25000 and counts.get("MUNICIPIO", 0) >= 12

            # Vistas analíticas y MV
            cur.execute(
                "SELECT object_name, object_type, status FROM user_objects "
                "WHERE object_name IN ('VW_CALENDARIO_MES', 'VW_INGRESO_RESERVA', "
                "'VW_INGRESO_HOSPEDAJE_TEMPORADA', 'VW_OCUPACION_MENSUAL_BASE', 'MV_OCUPACION_MENSUAL')"
            )
            for obj_name, obj_type, obj_status in cur.fetchall():
                if obj_name in ANALYTIC_VIEWS and obj_status == "VALID":
                    status["analytic_views_valid"].append(obj_name)
                if obj_name == "MV_OCUPACION_MENSUAL" and obj_type == "MATERIALIZED VIEW":
                    status["mv_status"] = obj_status

            # Migración 002 (columnas de soporte PL/SQL)
            cur.execute(
                "SELECT COUNT(*) FROM user_tab_columns "
                "WHERE (table_name = 'AUDITORIA_TARIFA' AND column_name = 'ID_SENTENCIA') "
                "OR (table_name = 'LIQUIDACION_MENSUAL' AND column_name IN ('PORCENTAJE_COMISION', 'BASE_COMISION', 'CRITERIO_LIQUIDACION'))"
            )
            status["e2_migration_ready"] = cur.fetchone()[0] == 4

            # Objetos E2
            cur.execute(
                "SELECT object_name, object_type, status FROM user_objects "
                "WHERE object_name IN ('PKG_TURISMOUQ', 'TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA')"
            )
            for obj_name, obj_type, obj_status in cur.fetchall():
                if obj_status == "VALID":
                    status["e2_objects_valid"].append(f"{obj_name} ({obj_type})")

            cur.execute(
                "SELECT trigger_name FROM user_triggers "
                "WHERE trigger_name IN ('TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA') "
                "AND status = 'ENABLED'"
            )
            status["e2_triggers_enabled"] = [r[0] for r in cur.fetchall()]

            # Objetos E3
            cur.execute(
                "SELECT object_name, object_type, status FROM user_objects "
                "WHERE status = 'VALID' AND object_name IN ("
                "'PKG_RESERVA_PAGO_INTERNO', 'SP_RESERVA_CON_PAGO', 'TRG_SOLICITAR_RESERVA_PAGO', "
                "'V_E3_ALOJAMIENTOS', 'V_E3_HABITACIONES', 'V_E3_CLIENTES', "
                "'V_E3_TARIFAS_COTIZACION', 'V_E3_SOLICITUD_PAGO', 'V_E3_ADMIN_TARIFAS', "
                "'V_E3_GERENCIA_MENSUAL', 'V_E3_AUDITORIA_TARIFA')"
            )
            status["e3_objects_valid"] = [f"{r[0]} ({r[1]})" for r in cur.fetchall()]

            # Índices E3
            cur.execute(
                "SELECT index_name FROM user_indexes "
                "WHERE index_name IN ('IX_E3_RESERVA_ALOJ_CHECKIN', 'IX_E3_PAGO_DIA', 'IX_E3_RESERVA_ESTADO_CHECKOUT')"
            )
            status["e3_indexes_present"] = [r[0] for r in cur.fetchall()]

            # Objetos inválidos y errores de compilación
            cur.execute(
                "SELECT object_name, object_type FROM user_objects WHERE status <> 'VALID' ORDER BY object_name"
            )
            status["invalid_objects"] = [f"{r[0]} ({r[1]})" for r in cur.fetchall()]

            cur.execute(
                "SELECT name, type, line, position, text FROM user_errors WHERE attribute = 'ERROR' ORDER BY name, sequence"
            )
            status["user_errors"] = [
                {"objeto": r[0], "tipo": r[1], "linea": r[2], "posicion": r[3], "error": r[4]}
                for r in cur.fetchall()
            ]

        return status

    def run_script_step(
        self,
        label: str,
        relative_path: str,
        args: Optional[List[str]] = None,
        override_defines: Optional[Dict[str, str]] = None,
        connection: Optional[oracledb.Connection] = None,
    ) -> ExecutionStepResult:
        """Ejecuta un archivo SQL/PLSQL del repositorio y devuelve el resultado detallado."""
        t_start = time.perf_counter()
        script_path = (BASE_DIR / relative_path).resolve()

        def _run_on_conn(conn: oracledb.Connection) -> ExecutionStepResult:
            prev_timeout = getattr(conn, "call_timeout", 30_000)
            conn.call_timeout = 300_000
            session = SqlScriptSession(conn, base_dir=BASE_DIR)
            try:
                session.execute_file(script_path, args=args, override_defines=override_defines)
                elapsed = round((time.perf_counter() - t_start) * 1000, 2)
                return ExecutionStepResult(
                    label=label,
                    script_path=relative_path,
                    success=True,
                    elapsed_ms=elapsed,
                    statements_executed=session.statements_executed,
                    output_lines=session.output_lines,
                )
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                elapsed = round((time.perf_counter() - t_start) * 1000, 2)
                return ExecutionStepResult(
                    label=label,
                    script_path=relative_path,
                    success=False,
                    elapsed_ms=elapsed,
                    statements_executed=session.statements_executed,
                    output_lines=session.output_lines,
                    error_message=str(exc),
                )
            finally:
                conn.call_timeout = prev_timeout

        if connection is not None:
            return _run_on_conn(connection)

        with self.database.get_connection() as conn:
            return _run_on_conn(conn)

    def run_full_clean_install(
        self,
        semilla: int = 20262,
        referencia: str = "2026-10-22 12:00:00 America/Bogota",
        include_e3_indexes: bool = True,
        on_step_complete: Optional[Callable[[int, int, ExecutionStepResult], None]] = None,
    ) -> List[ExecutionStepResult]:
        """Ejecuta el pipeline completo de instalacion desde una base limpia (E1 -> E2 -> E3)."""
        steps: List[Tuple[str, str, Optional[Dict[str, str]]]] = [
            ("1. Modelo Físico DDL (22 Tablas)", "01_DDL_TURISMOUQ_ORACLE21C.sql", None),
            (
                "2. Carga Sintética y Verificación E1",
                "02_carga.sql",
                {"CARGA_SEMILLA": str(semilla), "CARGA_REFERENCIA": referencia},
            ),
            ("3. Vistas Analíticas y Vista Materializada", "scripts/preparar_analitica.sql", None),
            ("4. Refresco de Vista Materializada", "scripts/refrescar_ocupacion.sql", None),
            ("5. Capa PL/SQL y Triggers (Entrega 2)", "04_instalar_capa_plsql.sql", None),
            ("6. Reserva con Pago y Vistas de Seguridad (Entrega 3)", "06_instalar_entrega3.sql", None),
        ]
        if include_e3_indexes:
            steps.append(("7. Índices de Rendimiento y Estadísticas (Entrega 3)", "07_crear_indices_entrega3.sql", None))

        results: List[ExecutionStepResult] = []
        total = len(steps)
        with self.database.get_connection() as conn:
            for idx, (label, rel_path, defines) in enumerate(steps, start=1):
                res = self.run_script_step(
                    label=label,
                    relative_path=rel_path,
                    override_defines=defines,
                    connection=conn,
                )
                results.append(res)
                if on_step_complete:
                    on_step_complete(idx, total, res)
                if not res.success:
                    break
        return results

    def provision_owner_as_sysdba(
        self,
        sys_password: str,
        target_owner: str,
        owner_password: Optional[str] = None,
        configure_e3_roles: bool = False,
        create_demo_accounts: bool = False,
        demo_password: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """Ejecuta aprovisionamiento administrativo como SYSDBA (Tablespace, Permisos directos, Roles E3)."""
        owner_clean = target_owner.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", owner_clean):
            return False, ["Nombre de propietario Oracle inválido."]

        logs: List[str] = []
        try:
            conn = oracledb.connect(
                user="SYS",
                password=sys_password,
                dsn=self.database.dsn,
                mode=oracledb.AUTH_MODE_SYSDBA,
            )
        except Exception as exc:
            return False, [f"No fue posible conectar como SYSDBA: {exc}"]

        try:
            with conn.cursor() as cur:
                cur.execute("ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN'")

                # 1. Verificar o crear TS_HISTORICO_RESERVAS
                cur.execute(
                    "SELECT COUNT(*) FROM dba_tablespaces WHERE tablespace_name = 'TS_HISTORICO_RESERVAS'"
                )
                if cur.fetchone()[0] == 0:
                    cur.execute("SELECT value FROM v$parameter WHERE name = 'db_create_file_dest'")
                    omf_row = cur.fetchone()
                    omf_dest = omf_row[0].strip() if omf_row and omf_row[0] else ""
                    session = SqlScriptSession(conn, base_dir=BASE_DIR)
                    if omf_dest:
                        session.execute_file(
                            BASE_DIR / "scripts/crear_tablespace.sql", args=["OMF", "SIN_RUTA"]
                        )
                    else:
                        cur.execute(
                            "SELECT file_name FROM dba_data_files WHERE tablespace_name = 'USERS' FETCH FIRST 1 ROW ONLY"
                        )
                        users_file = cur.fetchone()[0]
                        sep = "\\" if "\\" in users_file else "/"
                        parent_dir = users_file.rsplit(sep, 1)[0]
                        ts_path = f"{parent_dir}{sep}ts_historico_reservas01.dbf"
                        session.execute_file(
                            BASE_DIR / "scripts/crear_tablespace.sql", args=["RUTA", ts_path]
                        )
                    logs.extend(session.output_lines)
                else:
                    logs.append("Tablespace TS_HISTORICO_RESERVAS ya existe y está disponible.")

                # 2. Verificar o crear usuario propietario
                cur.execute("SELECT COUNT(*) FROM dba_users WHERE username = :u", u=owner_clean)
                user_exists = cur.fetchone()[0] == 1
                if not user_exists:
                    if not owner_password:
                        return False, [f"El usuario {owner_clean} no existe; indique una contraseña para crearlo."]
                    cur.execute(
                        f'CREATE USER "{owner_clean}" IDENTIFIED BY "{owner_password}" '
                        f"DEFAULT TABLESPACE users TEMPORARY TABLESPACE temp QUOTA UNLIMITED ON users"
                    )
                    logs.append(f"Usuario propietario {owner_clean} creado.")
                elif owner_password:
                    cur.execute(f'ALTER USER "{owner_clean}" IDENTIFIED BY "{owner_password}" ACCOUNT UNLOCK')
                    logs.append(f"Contraseña actualizada y cuenta desbloqueada para {owner_clean}.")

                # 3. Conceder privilegios directos y cuotas requeridas por Entregas 1, 2 y 3
                cur.execute(
                    f"GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, "
                    f"CREATE MATERIALIZED VIEW, CREATE SEQUENCE, CREATE PROCEDURE, CREATE TRIGGER "
                    f'TO "{owner_clean}"'
                )
                cur.execute(f'ALTER USER "{owner_clean}" QUOTA UNLIMITED ON users')
                cur.execute(f'ALTER USER "{owner_clean}" QUOTA UNLIMITED ON ts_historico_reservas')
                logs.append(
                    f"Privilegios directos (CREATE TABLE, VIEW, MATERIALIZED VIEW, SEQUENCE, PROCEDURE, TRIGGER) y cuotas otorgados a {owner_clean}."
                )

                # 4. Opcional: Roles y cuentas de demostracion de Entrega 3
                if configure_e3_roles or create_demo_accounts:
                    cur.execute("ALTER SYSTEM SET RESOURCE_LIMIT = TRUE")
                    logs.append("Parámetro RESOURCE_LIMIT = TRUE habilitado.")

                if configure_e3_roles:
                    session_sec = SqlScriptSession(conn, base_dir=BASE_DIR)
                    session_sec.execute_file(
                        BASE_DIR / "08_configurar_seguridad_entrega3.sql", args=[owner_clean]
                    )
                    logs.extend(session_sec.output_lines)
                    logs.append(f"Roles y perfil de Entrega 3 configurados para {owner_clean}.")

                if create_demo_accounts:
                    session_acc = SqlScriptSession(conn, base_dir=BASE_DIR)
                    session_acc.execute_file(
                        BASE_DIR / "09_preparar_cuentas_entrega3.sql", args=[owner_clean]
                    )
                    logs.extend(session_acc.output_lines)
                    logs.append(f"Cuentas de demostración (_USR_RECEP, _USR_ADMIN, _USR_GERENTE, _USR_AUDITOR) creadas.")
                    if demo_password:
                        for suffix in ("USR_RECEP", "USR_ADMIN", "USR_GERENTE", "USR_AUDITOR"):
                            demo_usr = f"{owner_clean}_{suffix}"
                            cur.execute(f'ALTER USER "{demo_usr}" IDENTIFIED BY "{demo_password}" ACCOUNT UNLOCK')
                        logs.append("Contraseña asignada a las 4 cuentas de demostración.")

            return True, logs
        except Exception as exc:
            return False, logs + [f"Error durante el aprovisionamiento: {exc}"]
        finally:
            conn.close()


migrations_service = MigrationsService()
