"""Vista del Modulo de Liquidacion Mensual Contable (Cursor PL/SQL Entrega 2)."""
import streamlit as st
import pandas as pd
import plotly.express as px
from app.core.plsql_service import plsql_service

def render_liquidaciones():
    st.markdown("## 📑 Módulo de Liquidación Mensual Contable")
    st.caption("Proceso masivo de liquidación por alojamiento mediante cursor explícito parametrizado en `PKG_TURISMOUQ.sp_liquidar_mes`.")

    st.info(
        "**Regla de Negocio:** La liquidación contable considera únicamente reservas con estado `FINALIZADA` en el mes de su checkout. "
        "La comisión se calcula aplicando el porcentaje sobre la base de hospedaje más consumos de servicios."
    )

    col_l1, col_l2, col_l3, col_l4 = st.columns([1.5, 1.5, 2, 3])
    with col_l1:
        anio = st.selectbox("Año a Liquidar:", [2024, 2025, 2026], index=1, key="liq_anio")
    with col_l2:
        mes = st.selectbox("Mes a Liquidar:", list(range(1, 13)), index=1, key="liq_mes") # Febrero 2025 por defecto
    with col_l3:
        comision_pct = st.number_input("% Comisión Plataforma:", min_value=1.0, max_value=50.0, value=12.0, step=0.5, key="liq_pct")
    with col_l4:
        df_aloj = plsql_service.get_alojamientos()
        opciones_aloj = {"(Todos los alojamientos)": None}
        if not df_aloj.empty:
            for _, row in df_aloj.iterrows():
                opciones_aloj[f"{row['nombre']} ({row['municipio']})"] = int(row["id_alojamiento"])
        aloj_sel = st.selectbox("Filtro de Alojamiento:", list(opciones_aloj.keys()), key="liq_aloj_filter")
        id_aloj_filtro = opciones_aloj[aloj_sel]

    st.write("")
    if st.button("⚙️ Ejecutar Proceso de Liquidación en Oracle", type="primary", use_container_width=True):
        with st.spinner("Ejecutando cursor explícito pkg_turismouq.sp_liquidar_mes..."):
            ok, creadas, conservadas, msg = plsql_service.liquidar_mes(
                anio=anio,
                mes=mes,
                porcentaje_comision=comision_pct,
                id_alojamiento=id_aloj_filtro
            )
        if ok:
            st.success(f"✅ {msg}")
        else:
            st.error(f"❌ Fallo en la liquidación: {msg}")

    st.markdown("---")
    st.markdown("### 📊 Historial de Cortes Persistidos en `LIQUIDACION_MENSUAL`")

    df_liq = plsql_service.get_liquidaciones(limit=100)
    if not df_liq.empty:
        # Métricas consolidadas
        total_base = df_liq["base_total"].sum() if "base_total" in df_liq.columns else 0.0
        total_comision = df_liq["valor_comision"].sum() if "valor_comision" in df_liq.columns else 0.0
        total_neto = df_liq["valor_neto_propietario"].sum() if "valor_neto_propietario" in df_liq.columns else 0.0

        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            st.metric("Total Facturación Liquidada", f"${total_base:,.2f}")
        with col_k2:
            st.metric("Comisiones TurismoUQ", f"${total_comision:,.2f}")
        with col_k3:
            st.metric("Neto Transferido a Propietarios", f"${total_neto:,.2f}")

        # Gráfico de distribución de liquidaciones
        if "alojamiento" in df_liq.columns and "valor_neto_propietario" in df_liq.columns:
            fig = px.bar(
                df_liq.head(15),
                x="alojamiento",
                y=["valor_comision", "valor_neto_propietario"],
                title="Desglose de Liquidación: Comisión Plataforma vs Neto Propietario (Top 15)",
                barmode="stack",
                labels={"value": "Importe ($)", "alojamiento": "Alojamiento", "variable": "Concepto"},
                color_discrete_map={"valor_comision": "#ff7f0e", "valor_neto_propietario": "#2ca02c"}
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(df_liq, use_container_width=True, height=350)
    else:
        st.info("Aún no se han persistido liquidaciones mensuales en la base de datos para los criterios seleccionados.")
