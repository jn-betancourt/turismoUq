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
        
        esquemas_disp = ["TURISMOUQ_E2", "TURISMOUQ_E1", "TURISMOUQ", "Otro"]
        esquema_sel = st.selectbox("Esquema:", esquemas_disp, index=0)
        if esquema_sel == "Otro":
            db_user = st.text_input("Usuario personalizado:", value="")
        else:
            db_user = esquema_sel

        db_pass = st.text_input("Contraseña:", value=st.session_state.get("db_pass", DEFAULT_DB_PASSWORD), type="password")

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
        if btn_test or "db_status" in st.session_state:
            if btn_test:
                with st.spinner("Conectando con Oracle XE 21c..."):
                    ok, msg, meta = db_manager.test_connection()
                    st.session_state["db_status"] = (ok, msg, meta)
            
            ok, msg, meta = st.session_state["db_status"]
            if ok:
                is_connected = True
                st.markdown(f"<span class='status-badge status-online'>🟢 Conectado ({meta.get('latency_ms', 0)} ms)</span>", unsafe_allow_html=True)
                st.caption(f"**Usuario:** `{meta.get('user')}` | **PDB:** `{meta.get('container')}` | **Versión:** `{meta.get('version')}`")
            else:
                st.markdown("<span class='status-badge status-offline'>🔴 Sin Conexión</span>", unsafe_allow_html=True)
                st.caption(f"_{msg}_")
        else:
            st.caption("Presione 'Probar Conexión' para validar.")

        st.markdown("---")
        st.markdown("### 🧭 Navegación")
        menu = st.radio(
            "Seleccione un módulo:",
            [
                "📊 Dashboard Analítico (Consultas 1-8)",
                "🏨 Cotizador y Reservas (PL/SQL)",
                "📑 Liquidación Mensual Contable",
                "🛡️ Auditoría de Tarifas & Triggers",
                "📖 Documentación & Modelo"
            ]
        )

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

    # Renderizar vista seleccionada
    if menu == "📊 Dashboard Analítico (Consultas 1-8)":
        render_dashboard()
    elif menu == "🏨 Cotizador y Reservas (PL/SQL)":
        render_cotizador_reservas()
    elif menu == "📑 Liquidación Mensual Contable":
        render_liquidaciones()
    elif menu == "🛡️ Auditoría de Tarifas & Triggers":
        render_auditoria()
    elif menu == "📖 Documentación & Modelo":
        render_documentacion()

def render_documentacion():
    st.markdown("## 📖 Documentación del Proyecto y Modelo de Datos")
    st.markdown(
        """
        ### Arquitectura del Modelo
        El modelo de datos implementado en **Oracle XE 21c** se compone de **22 tablas normalizadas**, tablespace dedicado
        `TS_HISTORICO_RESERVAS`, volumen de datos reproducible (12 municipios, 60 alojamientos, 400 habitaciones,
        3.000 clientes, 25.000 reservas, 40.000 servicios) y capa de abstracción en PL/SQL.

        #### Componentes Principales:
        1. **DDL e Infraestructura:** Archivo `01_DDL_TURISMOUQ_ORACLE21C.sql` con PK, FK, CHECKs y particionamiento/tablespace.
        2. **Carga Sintética:** `02_carga.sql` con semillas reproducibles y captura de precios históricos por tramo.
        3. **Consultas Analíticas (Entrega 1):** 8 consultas de análisis con `PIVOT`, `ROLLUP`, `RANK() OVER`, `LAG()`, Variables de enlace, `MV_OCUPACION_MENSUAL` y `UNPIVOT`.
        4. **Capa PL/SQL (Entrega 2):** Paquete `PKG_TURISMOUQ` con `fn_valor_estadia`, `sp_crear_reserva` con manejo de excepciones `RAISE_APPLICATION_ERROR`, y cursor parametrizado en `sp_liquidar_mes`.
        5. **Auditoría e Integridad:** Tres triggers compuestos para auditoría de tarifas (`TRG_AUDITAR_TARIFA`) y prevención de solapamientos sin error de tabla mutante.
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
