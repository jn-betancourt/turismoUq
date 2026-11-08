"""Interfaz de caja y módulos de lectura o gestión según el rol Oracle."""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo

import oracledb
import streamlit as st

from app.core.entrega3_service import BookingPaymentRequest, Entrega3Service, PAYMENT_METHODS


def local_today() -> date:
    return datetime.now(ZoneInfo("America/Bogota")).date()


def render_payment_error(error: oracledb.DatabaseError) -> None:
    detail = error.args[0]
    code = getattr(detail, "code", 0)
    messages = {
        20304: "La habitación no está disponible para ese rango.",
        20305: "La cantidad de huéspedes supera la capacidad de la habitación.",
        20308: "Falta una temporada para una o más noches.",
        20310: "Falta una tarifa para una o más noches.",
        20312: "Otra operación tiene bloqueada la habitación. Vuelve a intentar.",
        20401: "El precio cambió. Actualiza la cotización antes de registrar el pago.",
    }
    st.error(messages.get(code, f"Oracle rechazó la operación (ORA-{code:05d})."))


def render_booking_payment(service: Entrega3Service) -> None:
    st.header("Reserva y pago")
    st.caption("Registra en Oracle un pago ya recibido y confirma la reserva en la misma operación.")
    lodgings = service.lodgings()
    if lodgings.empty:
        st.info("No hay alojamientos activos.")
        return
    lodging_names = {
        int(row.id_alojamiento): f"{row.nombre} · {row.municipio}" for row in lodgings.itertuples()
    }
    lodging_id = st.selectbox("Alojamiento", list(lodging_names), format_func=lodging_names.get)
    rooms = service.rooms(lodging_id)
    if rooms.empty:
        st.info("No hay habitaciones habilitadas en este alojamiento.")
        return
    room_names = {
        int(row.id_habitacion): f"{row.numero_habitacion} · {row.tipo_habitacion} · hasta {row.capacidad}"
        for row in rooms.itertuples()
    }
    room_id = st.selectbox("Habitación", list(room_names), format_func=room_names.get)
    capacity = int(rooms.loc[rooms.id_habitacion == room_id, "capacidad"].iloc[0])
    left, right = st.columns(2)
    today = local_today()
    check_in = left.date_input("Entrada", value=today)
    check_out = right.date_input("Salida", value=today + timedelta(days=1))
    guests = st.number_input("Huéspedes", min_value=1, max_value=capacity, value=1, step=1)
    document = st.text_input("Número de documento del cliente", max_chars=25).strip()
    method = st.selectbox("Medio de pago recibido", list(PAYMENT_METHODS))

    amount = None
    try:
        amount = service.quote(room_id, check_in, check_out)
        st.metric("Total de hospedaje", f"COP {amount:,.2f}")
        st.caption("La disponibilidad se verifica al registrar; la cotización no bloquea la habitación.")
    except ValueError as error:
        st.warning(str(error))

    if amount is not None and document:
        customer = service.find_customer(document)
        if customer.empty:
            st.warning("No encontré un cliente con ese documento.")
        else:
            customer_id = int(customer.iloc[0]["id_cliente"])
            st.write(f"Cliente: {customer.iloc[0]['nombre_completo']}")
            with st.form("e3_payment"):
                received = st.text_input("Monto recibido en COP", placeholder="Ejemplo: 125000.00")
                commit = st.checkbox("Confirmo que recibí el pago completo")
                preview, submit = st.columns(2)
                simulate = preview.form_submit_button("Simular operación")
                register = submit.form_submit_button("Registrar reserva y pago", type="primary")
            if register and not commit:
                st.warning("Confirma que recibiste el pago antes de registrarlo.")
            elif simulate or register:
                if register:
                    try:
                        paid_amount = Decimal(received.strip().replace(",", "."))
                    except InvalidOperation:
                        paid_amount = None
                    if paid_amount is None or not paid_amount.is_finite() or paid_amount != amount:
                        st.warning("El monto recibido debe coincidir con la cotización vigente.")
                        return
                # El token persiste si Oracle confirmó pero se perdió la respuesta.
                signature = (service.owner, customer_id, lodging_id, room_id, check_in,
                             check_out, guests, amount, method)
                pending = st.session_state.get("e3_pending_payment")
                if register and pending and pending[0] == signature:
                    token = pending[1]
                else:
                    token = uuid4()
                    if register:
                        st.session_state["e3_pending_payment"] = (signature, token)
                request = BookingPaymentRequest(
                    token, customer_id, lodging_id, room_id, check_in, check_out,
                    guests, amount, PAYMENT_METHODS[method],
                )
                try:
                    with st.spinner("Verificando disponibilidad y registrando la operación…"):
                        receipt = service.book_and_pay(request, commit=register)
                except oracledb.DatabaseError as error:
                    render_payment_error(error)
                else:
                    if register:
                        st.session_state.pop("e3_pending_payment", None)
                        st.success(f"Reserva #{receipt.reservation_id} confirmada · Pago #{receipt.payment_id}.")
                    else:
                        st.success("Simulación exitosa. No se guardó la reserva ni el pago.")

    with st.expander("Mis comprobantes recientes"):
        receipts = service.recent_receipts()
        if receipts.empty:
            st.caption("Todavía no tienes comprobantes.")
        else:
            st.dataframe(receipts, hide_index=True)


def render_tariff_administration(service: Entrega3Service) -> None:
    st.header("Administrar tarifas")
    room_id = st.number_input("ID de habitación", min_value=1, step=1)
    tariffs = service.tariffs(room_id)
    if tariffs.empty:
        st.info("No hay tarifas para la habitación indicada.")
        return
    tariff_id = st.selectbox("ID de tarifa", tariffs.id_tarifa.tolist())
    selected = tariffs[tariffs.id_tarifa == tariff_id].iloc[0]
    previous = Decimal(str(selected.precio_noche))
    st.caption(f"Temporada #{int(selected.id_temporada)} · Precio actual: COP {previous:,.2f}")
    with st.form(f"e3_tariff_{tariff_id}"):
        raw_price = st.number_input("Nuevo precio (COP)", min_value=0.01, max_value=99999999.99,
                                    value=float(previous), step=0.01, format="%.2f")
        save = st.form_submit_button("Guardar tarifa", type="primary")
    if save:
        price = Decimal(str(raw_price)).quantize(Decimal("0.01"))
        if price == previous:
            st.info("El precio coincide con el actual.")
        elif service.update_tariff(int(tariff_id), previous, price):
            st.success("Tarifa actualizada. El cambio quedó en la auditoría.")
        else:
            st.warning("La tarifa cambió en otra sesión. Actualiza la página y vuelve a intentarlo.")


def render_management(service: Entrega3Service) -> None:
    st.header("Resumen mensual")
    month = st.date_input("Mes de entrada", date(2025, 6, 1))
    report = service.monthly_report(month)
    if report.empty:
        st.info("No hay reservas para el mes seleccionado.")
    else:
        left, right = st.columns(2)
        left.metric("Reservas", f"{report.reservas.sum():,}")
        right.metric("Valor contratado", f"COP {report.valor_contratado.sum():,.2f}")
        st.dataframe(report, hide_index=True)


def render_audit_entrega3(service: Entrega3Service) -> None:
    st.header("Cambios de tarifa")
    st.caption("Últimos 100 cambios. Las fechas de los eventos nuevos se guardan en UTC.")
    report = service.audit_report()
    if report.empty:
        st.info("No hay cambios registrados.")
    else:
        st.dataframe(report, hide_index=True)
