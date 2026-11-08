"""Punto de entrada principal para la aplicacion Streamlit de TurismoUQ."""
import streamlit as st
from app.config import (
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_SERVICE,
    DEFAULT_DB_USER,
    DEFAULT_DB_PASSWORD,
    APP_DIR,
    BASE_DIR
)
from app.core.connection import db_manager
from app.core.entrega3_service import Entrega3Service, normalize_owner
from app.views.entrega3 import (
    render_audit_entrega3,
    render_booking_payment,
    render_management,
    render_payment_error,
    render_tariff_administration,
)
import oracledb
from app.views.dashboard_consultas import render_dashboard
from app.views.cotizador_reservas import render_cotizador_reservas
from app.views.liquidaciones import render_liquidaciones
from app.views.auditoria_tarifas import render_auditoria

def load_css():
    css_file = APP_DIR / "static" / "style.css"
    if css_file.exists():
        st.markdown(f"<style>{css_file.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

def main():
    st.set_page_config(
        page_title="TurismoUQ — Plataforma de Gestión y Analítica",
        page_icon="🌴",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    load_css()

    # Barra lateral de configuración y conexión
    with st.sidebar:
        st.markdown("## 🌴 TurismoUQ")
        st.caption("Plataforma de Reservas Turísticas del Quindío · BD II")
        st.markdown("---")

        st.markdown("### 🔌 Conexión Oracle 21c (Thin)")
        db_host = st.text_input("Host / IP:", value=st.session_state.get("db_host", DEFAULT_DB_HOST))
        db_port = st.number_input("Puerto:", value=st.session_state.get("db_port", DEFAULT_DB_PORT), step=1)
        db_service = st.text_input("Servicio / PDB:", value=st.session_state.get("db_service", DEFAULT_DB_SERVICE))
        
        default_account = DEFAULT_DB_USER if DEFAULT_DB_USER in ("TURISMOUQ_E3", "TURISMOUQ_E2", "TURISMOUQ_E1", "TURISMOUQ") else "Otro"
        accounts = ["TURISMOUQ_E3", "TURISMOUQ_E2", "TURISMOUQ_E1", "TURISMOUQ", "Otro"]
        account = st.selectbox("Cuenta Oracle:", accounts, index=accounts.index(default_account))
        if account == "Otro":
            db_user = st.text_input("Usuario personalizado:", value=DEFAULT_DB_USER if default_account == "Otro" else "")
            owner = st.text_input("Esquema propietario:", value="TURISMOUQ_E3")
        else:
            db_user = owner = account

        db_pass = st.text_input("Contraseña:", value=st.session_state.get("db_pass", DEFAULT_DB_PASSWORD), type="password")

        # Una validacion anterior solo sirve para los mismos datos de conexion.
        connection_settings = (
            db_host.strip(), int(db_port), db_service.strip(), db_user.strip(), db_pass, owner.strip().upper()
        )
        if st.session_state.get("db_connection_settings") != connection_settings:
            st.session_state.pop("db_status", None)
            st.session_state.pop("e3_pending_payment", None)
            st.session_state["db_connection_settings"] = connection_settings

        # Actualizar credenciales en el manager
        db_manager.update_credentials(
            host=db_host,
            port=db_port,
            service_name=db_service,
            user=db_user,
            password=db_pass
        )

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            btn_test = st.button("Probar Conexión", use_container_width=True)
        with col_c2:
            btn_save = st.button("Guardar", use_container_width=True)

        if btn_save:
            st.session_state["db_host"] = db_host
            st.session_state["db_port"] = db_port
            st.session_state["db_service"] = db_service
            st.session_state["db_user"] = db_user
            st.session_state["db_pass"] = db_pass
            st.success("Configuración guardada en sesión.")

        # Test de conexión
        is_connected = False
        access = {}
        entrega3 = None
        if btn_test or "db_status" in st.session_state:
            if btn_test:
                if not all(connection_settings):
                    st.session_state["db_status"] = (
                        False, "Complete host, puerto, servicio, usuario y contraseña.", {}
                    )
                else:
                    with st.spinner("Conectando con Oracle XE 21c..."):
                        ok, msg, meta = db_manager.test_connection()
                        if ok:
                            try:
                                meta["access"] = Entrega3Service(db_manager, normalize_owner(owner)).access()
                            except (ValueError, oracledb.DatabaseError) as error:
                                ok, msg = False, str(error).splitlines()[0]
                        st.session_state["db_status"] = (ok, msg, meta)
            
            ok, msg, meta = st.session_state["db_status"]
            if ok:
                is_connected = True
                access = meta["access"]
                entrega3 = Entrega3Service(db_manager, owner)
                if access["roles"]:
                    st.caption("Roles: " + ", ".join(access["roles"]))
                st.markdown(f"<span class='status-badge status-online'>🟢 Conectado ({meta.get('latency_ms', 0)} ms)</span>", unsafe_allow_html=True)
                st.caption(f"**Usuario:** `{meta.get('user')}` | **PDB:** `{meta.get('container')}` | **Versión:** `{meta.get('version')}`")
            else:
                st.markdown("<span class='status-badge status-offline'>🔴 Sin Conexión</span>", unsafe_allow_html=True)
                st.caption(f"_{msg}_")
        else:
            st.caption("Presione 'Probar Conexión' para validar.")

        st.markdown("---")
        st.markdown("### 🧭 Navegación")
        modules = {}
        for permission, label, renderer in (
            ("booking", "Reserva y pago · Entrega 3", render_booking_payment),
            ("administration", "Administrar tarifas", render_tariff_administration),
            ("management", "Resumen mensual", render_management),
            ("audit", "Cambios de tarifa", render_audit_entrega3),
        ):
            if access.get(permission):
                modules[label] = (renderer, (entrega3,))
        if access.get("legacy"):
            modules.update({
                "📊 Dashboard Analítico (Consultas 1-8)": (render_dashboard, ()),
                "🏨 Cotizador y Reservas (PL/SQL)": (render_cotizador_reservas, ()),
                "📑 Liquidación Mensual Contable": (render_liquidaciones, ()),
                "🛡️ Auditoría de Tarifas & Triggers": (render_auditoria, ()),
            })
        documentation = "📖 Documentación & Modelo"
        modules[documentation] = (render_documentacion, ())
        menu = st.radio("Seleccione un módulo:", list(modules))

        st.markdown("---")
        st.caption("Universidad del Quindío · 2026-2\nBases de Datos II (Código 12338)")

    # Encabezado principal
    st.markdown(
        """
        <div class="main-header">
            <h1>TurismoUQ — Plataforma de Gestión y Analítica</h1>
            <p>Sistema desacoplado de interacción y visualización sobre Oracle Database XE 21c</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    if not is_connected:
        st.info("Complete los datos de conexión y presione «Probar Conexión» para abrir los módulos.")
    elif len(modules) == 1:
        st.info("La cuenta no tiene módulos habilitados para el esquema indicado.")

    renderer, arguments = modules[menu]
    try:
        renderer(*arguments)
    except oracledb.DatabaseError as error:
        render_payment_error(error)

def render_documentacion():
    st.markdown("## 📖 Documentación del Proyecto y Modelo de Datos")
    st.markdown(
        """
        ### Arquitectura del Modelo
        El modelo de datos implementado en **Oracle XE 21c** tiene **22 tablas base** y una tabla de solicitudes de pago en Entrega 3, tablespace dedicado
        `TS_HISTORICO_RESERVAS`, volumen de datos reproducible (12 municipios, 60 alojamientos, 400 habitaciones,
        3.000 clientes, 25.000 reservas, 40.000 servicios) y capa de abstracción en PL/SQL.

        #### Componentes Principales:
        1. **DDL e Infraestructura:** Archivo `01_DDL_TURISMOUQ_ORACLE21C.sql` con PK, FK, CHECKs y un tablespace para el histórico de reservas.
        2. **Carga Sintética:** `02_carga.sql` con semillas reproducibles y captura de precios históricos por tramo.
        3. **Consultas Analíticas (Entrega 1):** 8 consultas de análisis con `PIVOT`, `ROLLUP`, `RANK() OVER`, `LAG()`, Variables de enlace, `MV_OCUPACION_MENSUAL` y `UNPIVOT`.
        4. **Capa PL/SQL (Entrega 2):** Paquete `PKG_TURISMOUQ` con `fn_valor_estadia`, `sp_crear_reserva` con manejo de excepciones `RAISE_APPLICATION_ERROR`, y cursor parametrizado en `sp_liquidar_mes`.
        5. **Auditoría e Integridad:** Tres triggers compuestos para auditoría de tarifas (`TRG_AUDITAR_TARIFA`) y prevención de solapamientos sin error de tabla mutante.
        6. **Entrega 3:** reserva y pago atómicos, roles con vistas separadas y medición de planes de Oracle.
        """
    )

    with st.expander("📄 Ver Estructura de Entidades del Modelo (DBML)", expanded=False):
        dbml_path = BASE_DIR / "schema.dbml"
        if dbml_path.exists():
            st.code(dbml_path.read_text(encoding="utf-8"), language="text")
        else:
            st.info("Archivo schema.dbml no encontrado.")

if __name__ == "__main__":
    main()
