"""Vista del Dashboard Analitico para las 8 consultas de Entrega 1."""
import datetime as dt
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from app.config import CONSULTAS_INFO
from app.core.queries_service import queries_service

def render_dashboard():
    st.markdown("## 📊 Dashboard Analítico — Consultas de Análisis (Entrega 1)")
    st.caption("Abstracción interactiva de las 8 consultas analíticas obligatorias de TurismoUQ sobre Oracle XE 21c.")

    # Selector de consulta
    opciones = [f"{num}. {CONSULTAS_INFO[num]['titulo']}" for num in range(1, 9)]
    seleccion = st.selectbox("Seleccione la consulta a analizar:", opciones, index=0)
    query_num = int(seleccion.split(".")[0])
    info = CONSULTAS_INFO[query_num]

    # Ficha técnica de la consulta
    with st.expander("ℹ️ Ficha Técnica y Consulta SQL Original", expanded=False):
        col_t1, col_t2 = st.columns([1, 1])
        with col_t1:
            st.markdown(f"**Archivo:** `{info['archivo']}`")
            st.markdown(f"**Técnica:** `{info['tecnica']}`")
        with col_t2:
            st.markdown(f"**Descripción:** {info['descripcion']}")
        try:
            sql_text = queries_service.get_query_sql(query_num)
            st.code(sql_text, language="sql")
        except Exception as e:
            st.warning(f"No se pudo cargar el archivo SQL: {e}")

    st.markdown("---")

    # Controles específicos por consulta
    df = None
    elapsed_ms = 0.0
    clean_sql = ""

    if query_num == 5:
        st.markdown("### 🔍 Parámetros de Enlace (Binds)")
        col_f1, col_f2, col_btn = st.columns([2, 2, 1.5])
        with col_f1:
            fecha_ini = st.date_input("Fecha Inicio (Inclusiva):", value=dt.date(2025, 6, 1))
        with col_f2:
            fecha_fin = st.date_input("Fecha Fin (Inclusiva):", value=dt.date(2025, 7, 31))
        with col_btn:
            st.write("")
            st.write("")
            ejecutar = st.button("🚀 Ejecutar Consulta", use_container_width=True, type="primary")

        if ejecutar or "q5_executed" not in st.session_state:
            st.session_state["q5_executed"] = True
            try:
                with st.spinner("Ejecutando consulta parametrizada con binds..."):
                    df, elapsed_ms, clean_sql = queries_service.execute_query_5_parametrizada(
                        fecha_ini.isoformat(), fecha_fin.isoformat()
                    )
            except Exception as e:
                st.error(f"Error al ejecutar la consulta 5: {e}")
                return

    elif query_num == 6:
        st.markdown("### 🏢 Filtro de Ocupación Crítica sobre Vista Materializada")
        col_m1, col_m2, col_m3, col_ref = st.columns([1.5, 1.5, 2, 2])
        with col_m1:
            anio_sel = st.selectbox("Año:", [2024, 2025, 2026], index=1)
        with col_m2:
            mes_sel = st.selectbox("Mes:", list(range(1, 13)), index=11)  # Dic 2025 por defecto
        with col_m3:
            umbral = st.slider("Umbral Máximo de Ocupación (%):", min_value=5.0, max_value=100.0, value=30.0, step=5.0)
        with col_ref:
            st.write("")
            st.write("")
            refrescar_btn = st.button("🔄 Refrescar MV en DB", use_container_width=True)

        if refrescar_btn:
            with st.spinner("Ejecutando DBMS_MVIEW.REFRESH('MV_OCUPACION_MENSUAL', 'C')..."):
                ok, msg, ms = queries_service.refrescar_vista_materializada()
                if ok:
                    st.success(f"{msg}")
                else:
                    st.error(f"{msg}")

        try:
            with st.spinner("Consultando MV_OCUPACION_MENSUAL..."):
                df, elapsed_ms, clean_sql = queries_service.execute_query_6_critica(
                    anio=anio_sel, mes=mes_sel, umbral_pct=umbral
                )
        except Exception as e:
            st.error(f"Error al consultar la vista materializada: {e}")
            return

    else:
        # Consultas 1, 2, 3, 4, 7, 8
        col_run, _ = st.columns([2, 5])
        with col_run:
            if st.button("⚡ Ejecutar Consulta", type="primary", use_container_width=True):
                st.session_state[f"run_q{query_num}"] = True

        try:
            with st.spinner(f"Ejecutando consulta {query_num}..."):
                df, elapsed_ms, clean_sql = queries_service.execute_query(query_num)
        except Exception as e:
            st.error(f"Error al ejecutar la consulta {query_num}: {e}")
            return

    if df is not None:
        # Métricas de ejecución
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Total de Filas Obtenidas", f"{len(df):,}")
        with col_m2:
            st.metric("Tiempo de Respuesta en Motor", f"{elapsed_ms} ms")
        with col_m3:
            st.metric("Estado de Sesión", "GREGORIAN / READ COMMITTED")

        st.markdown("### 📈 Visualización Gráfica")

        # Visualizaciones personalizadas por consulta
        if query_num == 1:
            # PIVOT de ocupación
            meses_cols = [c for c in ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"] if c in df.columns]
            if "municipio" in df.columns and meses_cols:
                anios_disp = sorted(df["anio"].unique()) if "anio" in df.columns else []
                anio_f = st.selectbox("Filtrar Año para Heatmap:", anios_disp, index=len(anios_disp)-1 if anios_disp else 0)
                df_filtrado = df[df["anio"] == anio_f] if "anio" in df.columns else df
                df_pivot_hm = df_filtrado.set_index("municipio")[meses_cols]
                
                fig = px.imshow(
                    df_pivot_hm,
                    labels=dict(x="Mes", y="Municipio", color="% Ocupación"),
                    x=meses_cols,
                    y=df_pivot_hm.index,
                    color_continuous_scale="YlOrRd",
                    aspect="auto",
                    title=f"Mapa de Calor de Ocupación Hotelera (%) — Año {anio_f}"
                )
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 2:
            # ROLLUP de ingresos por municipio y tipo
            df_detalle = df[df["nivel_agregacion"] == 0] if "nivel_agregacion" in df.columns else df
            if not df_detalle.empty and "ingreso_hospedaje" in df_detalle.columns:
                fig = px.treemap(
                    df_detalle,
                    path=["municipio", "tipo_alojamiento", "temporada"],
                    values="ingreso_hospedaje",
                    color="ingreso_hospedaje",
                    color_continuous_scale="Viridis",
                    title="Distribución Jerárquica de Ingresos de Hospedaje (ROLLUP)"
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 3:
            # RANK de top alojamientos
            if "alojamiento" in df.columns and "ingreso_total" in df.columns:
                muni_disp = ["Todos"] + sorted(df["municipio"].unique().tolist())
                muni_sel = st.selectbox("Filtrar por Municipio:", muni_disp)
                df_rank = df if muni_sel == "Todos" else df[df["municipio"] == muni_sel]

                fig = px.bar(
                    df_rank,
                    x="ingreso_total",
                    y="alojamiento",
                    color="municipio",
                    orientation="h",
                    title=f"Top Alojamientos por Facturación Contratada ({muni_sel})",
                    labels={"ingreso_total": "Ingreso Total ($)", "alojamiento": "Establecimiento"},
                    text_auto=True
                )
                fig.update_layout(height=max(400, len(df_rank) * 25), yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 4:
            # Variación LAG
            if "mes" in df.columns and "ingreso" in df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df["mes"], y=df["ingreso"],
                    mode="lines+markers", name="Ingreso Contratado ($)",
                    line=dict(color="#1f77b4", width=3)
                ))
                if "ingreso_mes_anterior" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df["mes"], y=df["ingreso_mes_anterior"],
                        mode="lines", name="Mes Anterior (LAG 1)",
                        line=dict(color="#ff7f0e", dash="dot")
                    ))
                fig.update_layout(
                    title="Evolución Mensual del Ingreso y Comparación LAG",
                    xaxis_title="Mes de Check-in",
                    yaxis_title="Ingreso ($)",
                    hovermode="x unified",
                    height=450
                )
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 5:
            # Binds de consulta parametrizada
            if not df.empty and "ingreso_total" in df.columns:
                kpi1, kpi2, kpi3 = st.columns(3)
                with kpi1:
                    st.metric("Total Facturación en Rango", f"${df['ingreso_total'].sum():,.2f}")
                with kpi2:
                    st.metric("Total Reservas en Rango", f"{df['num_reservas'].sum():,}")
                with kpi3:
                    avg_ticket = df["ticket_promedio"].mean() if "ticket_promedio" in df.columns else 0.0
                    st.metric("Ticket Promedio General", f"${avg_ticket:,.2f}")

                fig = px.bar(
                    df.head(15),
                    x="alojamiento",
                    y="ingreso_total",
                    color="municipio",
                    title="Top 15 Alojamientos en el Rango Seleccionado",
                    labels={"ingreso_total": "Ingreso ($)", "alojamiento": "Alojamiento"}
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 6:
            # Vista Materializada ocupacion baja
            if not df.empty and "pct_ocupacion_bruta" in df.columns:
                fig = px.bar(
                    df,
                    x="pct_ocupacion_bruta",
                    y="alojamiento",
                    color="municipio",
                    orientation="h",
                    title=f"Alojamientos con Ocupación Crítica (< {umbral}%)",
                    labels={"pct_ocupacion_bruta": "Ocupación (%)", "alojamiento": "Alojamiento"}
                )
                fig.update_layout(height=max(400, len(df) * 25), yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 7:
            # UNPIVOT
            if "concepto" in df.columns and "valor" in df.columns:
                fig = px.bar(
                    df,
                    x="municipio",
                    y="valor",
                    color="concepto",
                    barmode="stack",
                    title="Composición de Ingresos: Hospedaje vs Servicios (UNPIVOT)",
                    labels={"valor": "Valor Contratado ($)", "municipio": "Municipio"}
                )
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)

        elif query_num == 8:
            # Anticipación y Cancelaciones
            if "tipo_temporada" in df.columns and "pct_cancelacion" in df.columns:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df["tipo_temporada"], y=df["pct_cancelacion"],
                    name="% Tasa de Cancelación", marker_color="#d62728"
                ))
                if "anticipacion_mediana_dias" in df.columns:
                    fig.add_trace(go.Bar(
                        x=df["tipo_temporada"], y=df["anticipacion_mediana_dias"],
                        name="Anticipación Mediana (Días)", marker_color="#2ca02c"
                    ))
                fig.update_layout(
                    title="Comportamiento por Temporada: Cancelación vs Anticipación de Reserva",
                    barmode="group",
                    xaxis_title="Temporada del Check-in",
                    height=450
                )
                st.plotly_chart(fig, use_container_width=True)

        # Tabla de Datos
        st.markdown("### 📋 Tabla de Resultados Detallada")
        st.dataframe(df, use_container_width=True, height=350)

        # Descarga CSV
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Descargar Resultados en CSV",
            data=csv_bytes,
            file_name=f"consulta_{query_num}_{dt.date.today().isoformat()}.csv",
            mime="text/csv"
        )
