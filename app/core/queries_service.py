"""Servicio de abstraccion y ejecucion para las 8 consultas analiticas."""
import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import pandas as pd
from app.config import CONSULTAS_DIR, SCRIPTS_DIR, CONSULTAS_INFO
from app.core.connection import db_manager

def clean_sql_statement(raw_sql: str) -> str:
    """Limpia comentarios y terminadores para ejecucion con driver oracledb."""
    # Eliminar comentarios multilínea /* ... */
    sql = re.sub(r"/\*.*?\*/", "", raw_sql, flags=re.DOTALL)
    # Eliminar comentarios de una línea -- ...
    sql = re.sub(r"(?m)^\s*--[^\n]*$", "", sql)
    # Eliminar punto y coma final o barra de SQL*Plus
    sql = sql.strip().rstrip(";").rstrip("/").strip()
    return sql

class QueriesService:
    """Servicio para cargar y ejecutar las consultas de Entrega 1."""

    @staticmethod
    def get_query_sql(query_number: int) -> str:
        """Lee el archivo SQL canónico correspondiente a la consulta."""
        info = CONSULTAS_INFO.get(query_number)
        if not info:
            raise ValueError(f"Consulta número {query_number} no existe.")
        file_path = CONSULTAS_DIR / info["archivo"]
        if not file_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo {file_path}")
        return file_path.read_text(encoding="utf-8-sig")

    @staticmethod
    def execute_query(
        query_number: int,
        binds: Optional[Dict[str, Any]] = None,
        custom_sql: Optional[str] = None
    ) -> Tuple[pd.DataFrame, float, str]:
        """Ejecuta una de las 8 consultas analíticas y retorna un DataFrame con métricas de tiempo."""
        raw_sql = custom_sql if custom_sql else QueriesService.get_query_sql(query_number)
        clean_sql = clean_sql_statement(raw_sql)

        t_start = time.perf_counter()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if binds:
                    cur.execute(clean_sql, binds)
                else:
                    cur.execute(clean_sql)
                
                columns = [col[0].lower() for col in cur.description] if cur.description else []
                rows = cur.fetchall()
                elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
                df = pd.DataFrame(rows, columns=columns)
                return df, elapsed_ms, clean_sql

    @staticmethod
    def execute_query_5_parametrizada(fecha_ini: str, fecha_fin: str) -> Tuple[pd.DataFrame, float, str]:
        """Ejecuta la Consulta 5 con fechas de enlace en formato YYYY-MM-DD."""
        binds = {"fecha_ini": fecha_ini, "fecha_fin": fecha_fin}
        return QueriesService.execute_query(5, binds=binds)

    @staticmethod
    def execute_query_6_critica(
        anio: int = 2025,
        mes: int = 12,
        umbral_pct: float = 30.0
    ) -> Tuple[pd.DataFrame, float, str]:
        """Ejecuta la Consulta 6 sobre MV_OCUPACION_MENSUAL con umbral y mes configurables."""
        fecha_inicio_str = f"{anio:04d}-{mes:02d}-01"
        # Calcular mes siguiente
        if mes == 12:
            fecha_fin_str = f"{anio + 1:04d}-01-01"
        else:
            fecha_fin_str = f"{anio:04d}-{mes + 1:02d}-01"

        custom_sql = f"""
        WITH periodo_informe AS (
            SELECT DATE '{fecha_inicio_str}' AS fecha_inicio,
                   DATE '{fecha_fin_str}' AS fecha_fin_exclusiva
            FROM dual
        )
        SELECT m.nombre AS municipio,
               a.nombre AS alojamiento,
               TO_CHAR(mv.mes, 'YYYY-MM') AS mes,
               mv.noches_ocupadas,
               mv.noches_disponibles AS capacidad_noches_bruta,
               ROUND(mv.pct_ocupacion, 2) AS pct_ocupacion_bruta
        FROM mv_ocupacion_mensual mv
        JOIN alojamiento a ON a.id_alojamiento = mv.id_alojamiento
        JOIN municipio m ON m.id_municipio = mv.id_municipio
        CROSS JOIN periodo_informe p
        WHERE mv.mes >= p.fecha_inicio AND mv.mes < p.fecha_fin_exclusiva
          AND mv.pct_ocupacion < :umbral
        ORDER BY mv.pct_ocupacion, m.nombre, a.id_alojamiento, mv.mes
        """
        binds = {"umbral": umbral_pct}
        return QueriesService.execute_query(6, binds=binds, custom_sql=custom_sql)

    @staticmethod
    def refrescar_vista_materializada() -> Tuple[bool, str, float]:
        """Refresca explícitamente MV_OCUPACION_MENSUAL usando DBMS_MVIEW.REFRESH."""
        t_start = time.perf_counter()
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.callproc("DBMS_MVIEW.REFRESH", ["MV_OCUPACION_MENSUAL", "C"])
                conn.commit()
            elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
            return True, f"Vista materializada MV_OCUPACION_MENSUAL refrescada exitosamente en {elapsed_ms} ms.", elapsed_ms
        except Exception as exc:
            return False, f"Error al refrescar la vista materializada: {str(exc)}", 0.0

queries_service = QueriesService()
