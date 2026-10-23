"""Vista de Monitor de Auditoria de Tarifas y Triggers (Entrega 2 PL/SQL)."""
import streamlit as st
import pandas as pd
from app.core.plsql_service import plsql_service

def render_auditoria():
    st.markdown("## 🛡️ Monitor de Auditoría de Tarifas & Triggers")
    st.caption("Supervisión en tiempo real del trigger de auditoría a nivel de sentencia (`TRG_AUDITAR_TARIFA`).")

    st.info(
        "**Comportamiento del Disparador:** Ante cualquier modificación de precios (`UPDATE` sobre `TARIFA.precio_noche`), "
        "el trigger compuesto captura los pares de precios por fila y persiste los eventos en `AFTER STATEMENT` dentro de la tabla `AUDITORIA_TARIFA`, "
        "registrando el usuario de sesión, marca temporal UTC y un identificador único de sentencia."
    )

    with st.expander("🛠️ Simulador de Modificación de Tarifa (Probar Disparador)", expanded=True):
        st.markdown("Modifique el precio de una tarifa para comprobar cómo el trigger registra la operación en tiempo real.")
        col_t1, col_t2, col_t3 = st.columns([2, 2, 2])
        with col_t1:
            tarifa_id = st.number_input("ID de Tarifa:", min_value=1, max_value=50000, value=1, step=1)
        with col_t2:
            nuevo_precio = st.number_input("Nuevo Precio por Noche ($):", min_value=10000.0, max_value=2000000.0, value=155000.0, step=5000.0)
        with col_t3:
            st.write("")
            st.write("")
            btn_update = st.button("💾 Actualizar Tarifa en Oracle", type="primary", use_container_width=True)

        if btn_update:
            with st.spinner("Ejecutando UPDATE sobre TARIFA..."):
                ok, msg = plsql_service.actualizar_tarifa(tarifa_id, nuevo_precio)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")

    st.markdown("---")
    st.markdown("### 📋 Registros Recientes en `AUDITORIA_TARIFA`")

    col_btn_ref, _ = st.columns([2, 6])
    with col_btn_ref:
        if st.button("🔄 Refrescar Registro de Auditoría", use_container_width=True):
            st.rerun()

    df_audit = plsql_service.get_auditorias(limit=100)
    if not df_audit.empty:
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Total Eventos Registrados", f"{len(df_audit)}")
        with col_m2:
            ultimo_usuario = df_audit["usuario"].iloc[0] if "usuario" in df_audit.columns else "N/A"
            st.metric("Último Actor Conectado", f"{ultimo_usuario}")
        with col_m3:
            ultima_fecha = df_audit["fecha_utc"].iloc[0] if "fecha_utc" in df_audit.columns else "N/A"
            st.metric("Última Modificación (UTC)", f"{ultima_fecha}")

        st.dataframe(df_audit, use_container_width=True, height=400)
    else:
        st.info("No se han registrado modificaciones de tarifas en `AUDITORIA_TARIFA` aún.")
