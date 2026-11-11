"""Vista del Modulo de Instalacion, DDL y Migraciones para TurismoUQ."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from app.config import BASE_DIR
from app.core.connection import db_manager
from app.core.entrega3_service import Entrega3Service, normalize_owner
from app.core.migrations_service import ExecutionStepResult, migrations_service


def _refresh_sidebar_access() -> None:
    """Actualiza el estado de acceso en session_state para habilitar nuevos modulos tras instalar."""
    settings = st.session_state.get("db_connection_settings")
    if not settings:
        return
    owner = settings[5]
    ok, msg, meta = db_manager.test_connection()
    if ok:
        try:
            meta["access"] = Entrega3Service(db_manager, normalize_owner(owner)).access()
        except Exception:
            meta["access"] = {"legacy": True, "migrations": True, "roles": []}
    st.session_state["db_status"] = (ok, msg, meta)


def _record_result(res: ExecutionStepResult) -> None:
    history = st.session_state.setdefault("migration_execution_history", [])
    history.insert(0, res)


def _render_step_feedback(res: ExecutionStepResult) -> None:
    if res.success:
        st.success(
            f"✅ **{res.label}** (`{res.script_path}`) completado en **{res.elapsed_ms:,.2f} ms** "
            f"({res.statements_executed} sentencias ejecutadas)."
        )
    else:
        st.error(
            f"❌ **{res.label}** (`{res.script_path}`) falló tras {res.elapsed_ms:,.2f} ms "
            f"({res.statements_executed} sentencias previas ejecutadas):\n\n`{res.error_message}`"
        )
    if res.output_lines:
        with st.expander("📋 Salida DBMS_OUTPUT / Mensajes del Script", expanded=not res.success):
            st.code("\n".join(res.output_lines), language="text")


def render_migraciones() -> None:
    st.markdown("## 🗄️ Módulo de Instalación, DDL y Migraciones")
    st.caption(
        "Ejecución controlada de DDL, carga sintética, vistas analíticas, migraciones estructurales y capas PL/SQL (Entregas 1, 2 y 3) sobre una base de datos limpia o en evolución."
    )

    try:
        status = migrations_service.get_schema_status()
    except Exception as exc:
        st.error(f"No fue posible consultar el diagnóstico del esquema: {exc}")
        return

    # --------------------------------------------------------------------------
    # RESUMEN DE DIAGNÓSTICO DEL ESQUEMA
    # --------------------------------------------------------------------------
    col_hdr1, col_hdr2 = st.columns([4, 1.2])
    with col_hdr1:
        st.markdown(
            f"**Esquema conectado:** `{status['connected_user']}` · "
            f"**Contenedor:** `{status['container']}` · "
            f"**Tablespace `TS_HISTORICO_RESERVAS`:** "
            f"{'🟢 Disponible' if status['tablespace_ready'] else '🔴 Ausente o sin cuota'}"
        )
    with col_hdr2:
        if st.button("🔄 Actualizar Estado", use_container_width=True):
            _refresh_sidebar_access()
            st.rerun()

    if status["is_admin"]:
        st.warning(
            "⚠️ Estás conectado como `SYS` / `SYSTEM`. Los scripts de modelo y PL/SQL rechazan instalarse sobre cuentas administrativas. "
            "Usa la pestaña **🔐 Aprovisionamiento Administrativo (SYSDBA)** para preparar tu usuario propietario (ej. `TURISMOUQ` o `TURISMOUQ_E3`) y luego conéctate con esa cuenta."
        )
    elif status["missing_direct_privs"]:
        st.warning(
            "⚠️ Faltan privilegios directos en `USER_SYS_PRIVS` requeridos por los verificadores del proyecto: "
            f"`{', '.join(status['missing_direct_privs'])}`. "
            "Puedes otorgarlos en 1 clic desde la pestaña **🔐 Aprovisionamiento Administrativo (SYSDBA)**."
        )

    if not status["is_admin"] and status["tables_22_count"] == 0:
        st.info(
            "✨ **Base de datos limpia detectada (0 tablas):** El esquema está listo para ser inicializado. "
            "Puedes ejecutar la **Instalación Completa en 1 Clic** o ejecutar cada etapa en orden."
        )

    # Tarjetas de semáforo por componente
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        st.metric("1. Tablas DDL E1", f"{status['tables_22_count']} / 22")
    with m2:
        reservas_n = status["table_row_counts"].get("RESERVA", 0)
        st.metric("2. Carga (Reservas)", f"{reservas_n:,}")
    with m3:
        mv_txt = " + MV" if status["mv_status"] == "VALID" else ""
        st.metric("3. Vistas E1", f"{len(status['analytic_views_valid'])} / 4{mv_txt}")
    with m4:
        st.metric("4. Objetos PL/SQL E2", f"{len(status['e2_objects_valid'])} / 5")
    with m5:
        st.metric("5. Objetos Entrega 3", f"{len(status['e3_objects_valid'])} / 11")
    with m6:
        st.metric("6. Índices E3", f"{len(status['e3_indexes_present'])} / 3")

    if status["user_errors"]:
        with st.expander("⚠️ Errores de compilación detectados en USER_ERRORS", expanded=True):
            st.dataframe(pd.DataFrame(status["user_errors"]), use_container_width=True)

    st.markdown("---")

    tab_guided, tab_migrations, tab_admin, tab_logs = st.tabs(
        [
            "🚀 Instalación en Base Limpia (DDL + Carga + Capas)",
            "🔄 Migraciones Estructurales (migraciones/)",
            "🔐 Aprovisionamiento Administrativo (SYSDBA)",
            "📜 Registro de Ejecución e Inspector SQL",
        ]
    )

    # ==========================================================================
    # TAB 1: INSTALACIÓN GUIADA (COMPLETA O PASO A PASO)
    # ==========================================================================
    with tab_guided:
        st.markdown("### ⚡ Opción A: Instalación Completa Automatizada sobre Base Limpia")
        st.caption(
            "Ejecuta en secuencia: `01_DDL` → `02_carga` (con verificación E1) → `preparar_analitica` → `refrescar_ocupacion` → `04_instalar_capa_plsql` → `06_instalar_entrega3` → `07_crear_indices_entrega3`."
        )

        col_p1, col_p2, col_p3 = st.columns([1.2, 2.2, 1.6])
        with col_p1:
            semilla_input = st.number_input(
                "Semilla (`carga_semilla`):",
                value=20262,
                step=1,
                key="mig_semilla",
            )
        with col_p2:
            referencia_input = st.text_input(
                "Referencia temporal (`carga_referencia`):",
                value="2026-10-22 12:00:00 America/Bogota",
                key="mig_ref",
            )
        with col_p3:
            st.write("")
            incluir_indices = st.checkbox(
                "Crear índices E3 (`07_crear_indices`)",
                value=True,
                help="Desmárcalo solo si deseas medir planes antes y después con medir_indices_entrega3.py.",
            )

        can_full_install = (
            not status["is_admin"]
            and status["tables_22_count"] == 0
            and status["tablespace_ready"]
        )
        if st.button(
            "🚀 Ejecutar Instalación Completa en Base Limpia (E1 + E2 + E3)",
            type="primary",
            use_container_width=True,
            disabled=not can_full_install,
        ):
            progress_bar = st.progress(0.0, text="Iniciando instalación completa...")
            status_box = st.empty()

            def _update_progress(idx: int, total: int, step_res: ExecutionStepResult) -> None:
                _record_result(step_res)
                pct = idx / total
                icon = "✅" if step_res.success else "❌"
                progress_bar.progress(
                    pct,
                    text=f"[{idx}/{total}] {icon} {step_res.label} ({step_res.elapsed_ms:,.0f} ms)",
                )

            results = migrations_service.run_full_clean_install(
                semilla=int(semilla_input),
                referencia=referencia_input.strip(),
                include_e3_indexes=incluir_indices,
                on_step_complete=_update_progress,
            )
            _refresh_sidebar_access()
            all_ok = all(r.success for r in results)
            if all_ok:
                status_box.success(
                    "🎉 **Instalación completa finalizada con éxito.** Las 22 tablas base, la carga de 25.000 reservas, las vistas analíticas, la capa PL/SQL (Entrega 2) y la capa de Entrega 3 están listas."
                )
            else:
                failed = next(r for r in results if not r.success)
                _render_step_feedback(failed)

        st.markdown("---")
        st.markdown("### 🧩 Opción B: Ejecución Individual por Etapa")
        st.caption(
            "Útil para instalar etapa por etapa o completar las entregas faltantes sobre un esquema parcialmente preparado."
        )

        etapas = [
            (
                "Etapa 1 · Modelo Físico DDL (22 Tablas)",
                "01_DDL_TURISMOUQ_ORACLE21C.sql",
                "Crea las 22 tablas normalizadas, PK, FK, UNIQUE, CHECK e índices base. Requiere esquema vacío.",
                None,
                status["tables_22_count"] == 22,
            ),
            (
                "Etapa 2 · Carga Sintética y Certificación E1",
                "02_carga.sql",
                "Genera 12 municipios, 60 alojamientos, 400 habitaciones, 3.000 clientes, 25.000 reservas y >40.000 servicios, y ejecuta verificar_entrega1.sql.",
                {"CARGA_SEMILLA": str(int(semilla_input)), "CARGA_REFERENCIA": referencia_input.strip()},
                status["data_loaded"],
            ),
            (
                "Verificador · Certificar Estructura y Datos Entrega 1",
                "scripts/verificar_entrega1.sql",
                "Comprueba de solo lectura las 22 tablas, volúmenes mínimos, tramos tarifarios y ausencia de solapamientos.",
                None,
                status["data_loaded"] and status["tables_22_count"] == 22,
            ),
            (
                "Etapa 3 · Vistas Analíticas y Vista Materializada",
                "scripts/preparar_analitica.sql",
                "Crea VW_CALENDARIO_MES, VW_INGRESO_RESERVA, VW_INGRESO_HOSPEDAJE_TEMPORADA, VW_OCUPACION_MENSUAL_BASE y MV_OCUPACION_MENSUAL.",
                None,
                len(status["analytic_views_valid"]) == 4 and status["mv_status"] == "VALID",
            ),
            (
                "Mantenimiento · Refrescar Vista Materializada (COMPLETE)",
                "scripts/refrescar_ocupacion.sql",
                "Ejecuta DBMS_MVIEW.REFRESH('MV_OCUPACION_MENSUAL', 'C') y registra su estado.",
                None,
                status["mv_status"] == "VALID",
            ),
            (
                "Etapa 4 · Instalar Capa PL/SQL Entrega 2",
                "04_instalar_capa_plsql.sql",
                "Ejecuta preflight E2, migración 002, paquete PKG_TURISMOUQ, los 3 triggers compuestos y verificar_entrega2.sql.",
                None,
                len(status["e2_objects_valid"]) == 5 and len(status["e2_triggers_enabled"]) == 3,
            ),
            (
                "Verificador · Certificar Compilación PL/SQL Entrega 2",
                "scripts/verificar_entrega2.sql",
                "Comprueba que PKG_TURISMOUQ y los 3 triggers compuestos estén VALID y ENABLED sin errores en USER_ERRORS.",
                None,
                len(status["e2_objects_valid"]) == 5,
            ),
            (
                "Etapa 5 · Instalar Capa Transaccional y Vistas Entrega 3",
                "06_instalar_entrega3.sql",
                "Aplica migración 003 (SOLICITUD_PAGO), SP_RESERVA_CON_PAGO, las 8 vistas V_E3_* y TRG_SOLICITAR_RESERVA_PAGO.",
                None,
                len(status["e3_objects_valid"]) == 11,
            ),
            (
                "Etapa 6 · Crear Índices y Estadísticas Entrega 3",
                "07_crear_indices_entrega3.sql",
                "Crea IX_E3_RESERVA_ALOJ_CHECKIN, IX_E3_PAGO_DIA, IX_E3_RESERVA_ESTADO_CHECKOUT y ejecuta DBMS_STATS.",
                None,
                len(status["e3_indexes_present"]) == 3,
            ),
        ]

        for idx, (titulo, rel_path, desc, defs, is_done) in enumerate(etapas):
            with st.container(border=True):
                c1, c2, c3 = st.columns([3.5, 1.2, 1.3])
                with c1:
                    badge = "🟢 Instalado / Verificado" if is_done else "⚪ Pendiente"
                    st.markdown(f"**{titulo}** — `{rel_path}` ({badge})")
                    st.caption(desc)
                with c2:
                    if st.button("📄 Ver SQL", key=f"view_sql_step_{idx}", use_container_width=True):
                        st.session_state[f"show_sql_step_{idx}"] = not st.session_state.get(
                            f"show_sql_step_{idx}", False
                        )
                with c3:
                    if st.button(
                        "▶️ Ejecutar",
                        key=f"run_step_{idx}",
                        type="primary" if not is_done else "secondary",
                        use_container_width=True,
                        disabled=status["is_admin"],
                    ):
                        with st.spinner(f"Ejecutando {rel_path}..."):
                            res = migrations_service.run_script_step(
                                label=titulo,
                                relative_path=rel_path,
                                override_defines=defs,
                            )
                            _record_result(res)
                            _refresh_sidebar_access()
                        _render_step_feedback(res)

                if st.session_state.get(f"show_sql_step_{idx}", False):
                    sql_file = BASE_DIR / rel_path
                    if sql_file.exists():
                        st.code(sql_file.read_text(encoding="utf-8-sig"), language="sql")

    # ==========================================================================
    # TAB 2: MIGRACIONES ESTRUCTURALES E INCREMENTALES (migraciones/)
    # ==========================================================================
    with tab_migrations:
        st.markdown("### 🔄 Scripts de Migración Estructural (`migraciones/`)")
        st.caption(
            "Permiten evolucionar esquemas preexistentes sin borrar datos ni alterar importes históricos."
        )

        migraciones_list = [
            (
                "Migración 001 · Tabla de Tramos Tarifarios (Entrega 1)",
                "migraciones/001_tramos_tarifarios.sql",
                "Actualiza un esquema de 21 a 22 tablas creando RESERVA_HABITACION_TARIFA_APLICADA y su índice si no existen, verificando su contrato.",
                status["has_tramos_table"],
            ),
            (
                "Migración 002 · Soporte PL/SQL de Auditoría y Liquidación (Entrega 2)",
                "migraciones/002_soporte_plsql.sql",
                "Amplía AUDITORIA_TARIFA (USUARIO_ORACLE a 128, ID_SENTENCIA RAW) y agrega metadatos de comisión en LIQUIDACION_MENSUAL.",
                status["e2_migration_ready"],
            ),
            (
                "Migración 003 · Bitácora de Solicitud de Pago (Entrega 3)",
                "migraciones/003_solicitud_pago.sql",
                "Crea la tabla SOLICITUD_PAGO para vincular el token del usuario conectado con su comprobante de pago.",
                status["has_solicitud_pago_table"],
            ),
        ]

        for idx, (m_title, m_path, m_desc, m_done) in enumerate(migraciones_list):
            with st.container(border=True):
                mc1, mc2 = st.columns([4, 1.5])
                with mc1:
                    badge = "🟢 Aplicada" if m_done else "⚪ Pendiente"
                    st.markdown(f"**{m_title}** (`{m_path}`) — {badge}")
                    st.caption(m_desc)
                with mc2:
                    if st.button(
                        "▶️ Aplicar Migración",
                        key=f"btn_mig_{idx}",
                        type="primary" if not m_done else "secondary",
                        use_container_width=True,
                        disabled=status["is_admin"],
                    ):
                        with st.spinner(f"Ejecutando {m_path}..."):
                            res = migrations_service.run_script_step(
                                label=m_title,
                                relative_path=m_path,
                            )
                            _record_result(res)
                            _refresh_sidebar_access()
                        _render_step_feedback(res)

                with st.expander(f"Ver código de `{m_path}`"):
                    f_path = BASE_DIR / m_path
                    if f_path.exists():
                        st.code(f_path.read_text(encoding="utf-8-sig"), language="sql")

    # ==========================================================================
    # TAB 3: APROVISIONAMIENTO ADMINISTRATIVO (SYSDBA)
    # ==========================================================================
    with tab_admin:
        st.markdown("### 🔐 Aprovisionamiento de Infraestructura, Usuario y Roles (`SYSDBA`)")
        st.info(
            "Si estás levantando una instancia o contenedor limpio de Oracle XE 21c, aquí puedes crear el tablespace "
            "`TS_HISTORICO_RESERVAS`, otorgar los privilegios directos requeridos al propietario (`CREATE PROCEDURE`, `CREATE TRIGGER`, "
            "`CREATE MATERIALIZED VIEW`, etc.) e instalar los 4 roles y cuentas de demostración de Entrega 3."
        )

        col_adm1, col_adm2 = st.columns(2)
        with col_adm1:
            sys_pwd = st.text_input(
                "Contraseña de `SYS` (conexión `AS SYSDBA` en XEPDB1):",
                type="password",
                key="adm_sys_pwd",
            )
            target_owner = st.text_input(
                "Esquema Propietario Objetivo (ej. `TURISMOUQ` o `TURISMOUQ_E3`):",
                value=status["connected_user"] if not status["is_admin"] else "TURISMOUQ_E3",
                key="adm_target_owner",
            )
        with col_adm2:
            owner_new_pwd = st.text_input(
                "Contraseña para el propietario (requerida si el usuario aún no existe):",
                type="password",
                key="adm_owner_pwd",
            )
            cfg_roles_e3 = st.checkbox(
                "Ejecutar `08_configurar_seguridad_entrega3.sql` (4 roles + perfil E3)",
                value=False,
                help="Requiere que el propietario empiece por TURISMOUQ_ y tenga instalada la capa de Entrega 3.",
            )
            cfg_cuentas_e3 = st.checkbox(
                "Ejecutar `09_preparar_cuentas_entrega3.sql` (crear cuentas _USR_RECEP, _USR_ADMIN, _USR_GERENTE, _USR_AUDITOR)",
                value=False,
            )
            demo_pwd = ""
            if cfg_cuentas_e3:
                demo_pwd = st.text_input(
                    "Contraseña opcional para asignar a las 4 cuentas de demostración:",
                    type="password",
                    key="adm_demo_pwd",
                )

        if st.button(
            "🛠️ Ejecutar Aprovisionamiento Administrativo como SYSDBA",
            type="primary",
            use_container_width=True,
        ):
            if not sys_pwd:
                st.error("Ingresa la contraseña de `SYS` para conectar como `SYSDBA`.")
            else:
                with st.spinner("Ejecutando aprovisionamiento administrativo en XEPDB1..."):
                    ok, logs = migrations_service.provision_owner_as_sysdba(
                        sys_password=sys_pwd,
                        target_owner=target_owner,
                        owner_password=owner_new_pwd or None,
                        configure_e3_roles=cfg_roles_e3,
                        create_demo_accounts=cfg_cuentas_e3,
                        demo_password=demo_pwd or None,
                    )
                if ok:
                    st.success("✅ Aprovisionamiento administrativo completado.")
                    st.code("\n".join(logs), language="text")
                else:
                    st.error("❌ Error durante el aprovisionamiento administrativo.")
                    st.code("\n".join(logs), language="text")

    # ==========================================================================
    # TAB 4: REGISTRO DE EJECUCIÓN E INSPECTOR DE SCRIPTS
    # ==========================================================================
    with tab_logs:
        st.markdown("### 📜 Historial de Ejecución en la Sesión")
        history: list[ExecutionStepResult] = st.session_state.get("migration_execution_history", [])
        if not history:
            st.caption("Aún no se han ejecutado scripts en esta sesión.")
        else:
            if st.button("🗑️ Limpiar historial de sesión"):
                st.session_state["migration_execution_history"] = []
                st.rerun()
            for item in history:
                _render_step_feedback(item)
