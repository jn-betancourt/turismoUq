"""Vista del Cotizador Dinamico y Formalizacion de Reservas (Entrega 2 PL/SQL)."""
import datetime as dt
import streamlit as st
import pandas as pd
from app.core.plsql_service import plsql_service

def render_cotizador_reservas():
    st.markdown("## 🏨 Cotizador y Reservas — Capa PL/SQL (Entrega 2)")
    st.caption("Interacción directa con el paquete PL/SQL `PKG_TURISMOUQ` en Oracle XE 21c.")

    tab_cot, tab_res = st.tabs(["💰 Cotizador Multitemporada (fn_valor_estadia)", "📝 Crear Reserva (sp_crear_reserva)"])

    # --------------------------------------------------------------------------
    # TAB 1: COTIZADOR MULTITEMPORADA
    # --------------------------------------------------------------------------
    with tab_cot:
        st.markdown("### Cotizador Dinámico de Estadías")
        st.info("La función `fn_valor_estadia` evalúa noche a noche la temporada correspondiente y liquida el precio aplicando las tarifas vigentes.")

        df_aloj = plsql_service.get_alojamientos()
        if df_aloj.empty:
            st.warning("No se pudieron cargar los alojamientos desde la base de datos.")
            return

        col_a1, col_a2 = st.columns(2)
        with col_a1:
            aloj_dict = {f"{row['nombre']} ({row['municipio']})": int(row["id_alojamiento"]) for _, row in df_aloj.iterrows()}
            aloj_sel = st.selectbox("Seleccione el Alojamiento:", list(aloj_dict.keys()), key="cot_aloj")
            id_aloj = aloj_dict[aloj_sel]

        df_habs = plsql_service.get_habitaciones(id_alojamiento=id_aloj)
        with col_a2:
            if not df_habs.empty:
                hab_dict = {f"Hab #{row['numero_habitacion']} - {row['tipo_habitacion']} (Cap: {row['capacidad']})": int(row["id_habitacion"]) for _, row in df_habs.iterrows()}
                hab_sel = st.selectbox("Seleccione la Habitación:", list(hab_dict.keys()), key="cot_hab")
                id_hab = hab_dict[hab_sel]
            else:
                st.warning("No hay habitaciones disponibles para este alojamiento.")
                id_hab = None

        st.markdown("#### Rango de Fechas de la Estadía")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            f_in = st.date_input("Fecha de Check-in:", value=dt.date(2025, 6, 15), key="cot_fin")
        with col_f2:
            f_out = st.date_input("Fecha de Check-out:", value=dt.date(2025, 6, 20), key="cot_fout")

        if st.button("💵 Cotizar Estadía en Oracle", type="primary", key="btn_cotizar"):
            if not id_hab:
                st.error("Por favor seleccione una habitación válida.")
            else:
                with st.spinner("Invocando PKG_TURISMOUQ.fn_valor_estadia en Oracle XE 21c..."):
                    ok, valor, mensaje = plsql_service.cotizar_estadia(id_hab, f_in, f_out)

                if ok:
                    noches = (f_out - f_in).days
                    st.success(f"✅ {mensaje}")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        st.metric("Total Cotizado", f"${valor:,.2f}")
                    with col_m2:
                        st.metric("Noches a Pernoctar", f"{noches}")
                    with col_m3:
                        avg_noche = valor / max(1, noches)
                        st.metric("Promedio por Noche", f"${avg_noche:,.2f}")
                else:
                    st.error(f"❌ Fallo en la cotización: {mensaje}")

    # --------------------------------------------------------------------------
    # TAB 2: CREAR RESERVA
    # --------------------------------------------------------------------------
    with tab_res:
        st.markdown("### Formalización de Reservas")
        st.caption("Invoca `sp_crear_reserva` con validación estricta de aforo, no-solapamiento de fechas y cálculo monetario atómico.")

        df_clientes = plsql_service.get_clientes(limit=100)
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if not df_clientes.empty:
                cli_dict = {f"{row['nombre_completo']} ({row['tipo_documento']} {row['numero_documento']})": int(row["id_cliente"]) for _, row in df_clientes.iterrows()}
                cli_sel = st.selectbox("Cliente Solicitante:", list(cli_dict.keys()), key="res_cli")
                id_cliente = cli_dict[cli_sel]
            else:
                id_cliente = 1
                st.info("Cliente predeterminado #1")

        with col_r2:
            aloj_res_sel = st.selectbox("Alojamiento:", list(aloj_dict.keys()), key="res_aloj")
            id_aloj_res = aloj_dict[aloj_res_sel]

        col_rf1, col_rf2 = st.columns(2)
        with col_rf1:
            res_fin = st.date_input("Fecha Check-in:", value=dt.date(2027, 1, 14), key="res_fin")
        with col_rf2:
            res_fout = st.date_input("Fecha Check-out:", value=dt.date(2027, 1, 16), key="res_fout")

        df_habs_res = plsql_service.get_habitaciones(id_alojamiento=id_aloj_res)
        st.markdown("#### Selección de Habitación y Huéspedes")
        col_rh1, col_rh2 = st.columns(2)
        with col_rh1:
            if not df_habs_res.empty:
                hab_res_dict = {
                    f"Hab #{row['numero_habitacion']} (Capacidad: {row['capacidad']})": (int(row["id_habitacion"]), int(row["capacidad"]))
                    for _, row in df_habs_res.iterrows()
                }
                hab_res_sel = st.selectbox("Habitación a reservar:", list(hab_res_dict.keys()), key="res_hab_sel")
                id_hab_res, cap_hab = hab_res_dict[hab_res_sel]
            else:
                id_hab_res, cap_hab = None, 2

        with col_rh2:
            personas = st.number_input(
                f"Huéspedes en la habitación (Máx autorizado: {cap_hab}):",
                min_value=1,
                max_value=15,
                value=min(2, cap_hab),
                step=1
            )
            if personas > cap_hab:
                st.warning(f"⚠️ Atención: Has indicado {personas} personas, superando el aforo ({cap_hab}). El motor Oracle disparará la excepción `c_error_capacidad (-20305)`.")

        # Servicios complementarios
        st.markdown("#### Servicios Opcionales del Alojamiento")
        df_servicios = plsql_service.get_servicios(id_alojamiento=id_aloj_res)
        servicios_seleccionados = []
        if not df_servicios.empty:
            serv_cols = st.columns(min(3, len(df_servicios)))
            for i, (_, s_row) in enumerate(df_servicios.iterrows()):
                with serv_cols[i % len(serv_cols)]:
                    incluir = st.checkbox(f"{s_row['nombre']} (${s_row['precio']:,.0f})", key=f"srv_chk_{s_row['id_servicio']}")
                    if incluir:
                        cant = st.number_input(f"Cantidad {s_row['nombre']}:", min_value=1, max_value=20, value=1, key=f"srv_qty_{s_row['id_servicio']}")
                        servicios_seleccionados.append((int(s_row["id_servicio"]), int(cant)))

        st.markdown("---")
        col_sub1, col_sub2 = st.columns([2, 1])
        with col_sub1:
            modo_confirmar = st.toggle("Confirmar cambios en base de datos (COMMIT)", value=False, help="Desmarcado ejecuta SAVEPOINT y ROLLBACK para modo prueba.")
        with col_sub2:
            btn_crear = st.button("🚀 Crear Reserva con PL/SQL", type="primary", use_container_width=True)

        if btn_crear:
            if not id_hab_res:
                st.error("Seleccione una habitación válida.")
            else:
                lista_habs = [(id_hab_res, int(personas))]
                with st.spinner("Ejecutando PKG_TURISMOUQ.sp_crear_reserva..."):
                    ok, new_res_id, total_res, msg = plsql_service.crear_reserva(
                        id_cliente=id_cliente,
                        id_alojamiento=id_aloj_res,
                        fecha_in=res_fin,
                        fecha_out=res_fout,
                        habitaciones=lista_habs,
                        servicios=servicios_seleccionados,
                        confirmar=modo_confirmar
                    )

                if ok:
                    st.success(f"🎉 {msg}")
                    st.balloons()
                    kpi_r1, kpi_r2, kpi_r3 = st.columns(3)
                    with kpi_r1:
                        st.metric("ID de Reserva Creada", f"#{new_res_id}")
                    with kpi_r2:
                        st.metric("Total Liquidado en BD", f"${total_res:,.2f}")
                    with kpi_r3:
                        st.metric("Transacción", "CONFIRMADA (COMMIT)" if modo_confirmar else "SIMULADA (ROLLBACK)")
                else:
                    st.error(f"🛑 Rechazo por regla de negocio de Oracle:")
                    st.error(msg)
