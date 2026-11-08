CREATE OR REPLACE PACKAGE pkg_reserva_pago_interno AUTHID DEFINER
    ACCESSIBLE BY (PROCEDURE sp_reserva_con_pago, TRIGGER trg_solicitar_reserva_pago)
AS
PROCEDURE registrar(
    p_id_cliente IN NUMBER,
    p_id_alojamiento IN NUMBER,
    p_fecha_in IN DATE,
    p_fecha_out IN DATE,
    p_habitaciones IN pkg_turismouq.lista_solicitudes_habitacion,
    p_servicios IN pkg_turismouq.lista_solicitudes_servicio,
    p_monto IN NUMBER,
    p_metodo_pago IN VARCHAR2,
    p_id_reserva OUT NUMBER,
    p_id_pago OUT NUMBER,
    p_valor_total OUT NUMBER
);
END pkg_reserva_pago_interno;
/

CREATE OR REPLACE PACKAGE BODY pkg_reserva_pago_interno AS
PROCEDURE registrar(
    p_id_cliente IN NUMBER,
    p_id_alojamiento IN NUMBER,
    p_fecha_in IN DATE,
    p_fecha_out IN DATE,
    p_habitaciones IN pkg_turismouq.lista_solicitudes_habitacion,
    p_servicios IN pkg_turismouq.lista_solicitudes_servicio,
    p_monto IN NUMBER,
    p_metodo_pago IN VARCHAR2,
    p_id_reserva OUT NUMBER,
    p_id_pago OUT NUMBER,
    p_valor_total OUT NUMBER
) IS
    v_id_reserva reserva.id_reserva%TYPE;
    v_id_pago pago.id_pago%TYPE;
    v_total reserva.valor_total%TYPE;
BEGIN
    -- E2 bloquea habitaciones en orden y relee disponibilidad antes de escribir.
    pkg_turismouq.crear_reserva_en_sentencia(
        p_id_cliente, p_id_alojamiento, p_fecha_in, p_fecha_out,
        p_habitaciones, p_servicios, v_id_reserva, v_total
    );

    IF p_monto IS NULL OR p_monto <= 0 OR p_monto <> v_total THEN
        RAISE_APPLICATION_ERROR(-20401, 'El monto debe cubrir el total vigente de la reserva.');
    END IF;
    IF p_metodo_pago IS NULL OR p_metodo_pago NOT IN (
        'TARJETA_CREDITO', 'TARJETA_DEBITO', 'TRANSFERENCIA', 'PSE', 'EFECTIVO'
    ) THEN
        RAISE_APPLICATION_ERROR(-20402, 'Metodo de pago no admitido.');
    END IF;

    INSERT INTO pago (id_reserva, id_cliente, monto, metodo_pago, estado_pago)
    VALUES (v_id_reserva, p_id_cliente, p_monto, p_metodo_pago, 'APROBADO')
    RETURNING id_pago INTO v_id_pago;

    UPDATE reserva SET estado = 'CONFIRMADA' WHERE id_reserva = v_id_reserva;
    p_id_reserva := v_id_reserva;
    p_id_pago := v_id_pago;
    p_valor_total := v_total;
END registrar;
END pkg_reserva_pago_interno;
/

CREATE OR REPLACE PROCEDURE sp_reserva_con_pago(
    p_id_cliente IN NUMBER,
    p_id_alojamiento IN NUMBER,
    p_fecha_in IN DATE,
    p_fecha_out IN DATE,
    p_habitaciones IN pkg_turismouq.lista_solicitudes_habitacion,
    p_servicios IN pkg_turismouq.lista_solicitudes_servicio,
    p_monto IN NUMBER,
    p_metodo_pago IN VARCHAR2,
    p_id_reserva OUT NUMBER,
    p_id_pago OUT NUMBER,
    p_valor_total OUT NUMBER
) AUTHID DEFINER IS
BEGIN
    SAVEPOINT turismouq_reserva_con_pago;
    pkg_reserva_pago_interno.registrar(
        p_id_cliente, p_id_alojamiento, p_fecha_in, p_fecha_out, p_habitaciones,
        p_servicios, p_monto, p_metodo_pago, p_id_reserva, p_id_pago, p_valor_total
    );
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO turismouq_reserva_con_pago;
        RAISE;
END;
/
