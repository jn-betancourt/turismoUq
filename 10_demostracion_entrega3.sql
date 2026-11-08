-- Como propietario E3, en una sesion sin DML pendiente.
-- Fechas libres al final de la cobertura de la carga sintetica original.
SET DEFINE OFF
SET SERVEROUTPUT ON
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED;

DECLARE
    c_inicio CONSTANT DATE := DATE '2027-01-09';
    c_segundo_inicio CONSTANT DATE := DATE '2027-01-11';
    v_habitaciones pkg_turismouq.lista_solicitudes_habitacion :=
        pkg_turismouq.lista_solicitudes_habitacion();
    v_servicios pkg_turismouq.lista_solicitudes_servicio :=
        pkg_turismouq.lista_solicitudes_servicio();
    v_cliente NUMBER;
    v_habitacion NUMBER;
    v_alojamiento NUMBER;
    v_reserva NUMBER;
    v_pago NUMBER;
    v_total NUMBER;
    v_descartado NUMBER;
    v_otro_pago NUMBER;
    v_otro_total NUMBER;
    v_monto NUMBER;
    v_cantidad NUMBER;
    v_antes NUMBER;

    FUNCTION cantidad_reservas_segunda RETURN NUMBER IS
        v_resultado NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_resultado FROM reserva
        WHERE id_cliente = v_cliente AND id_alojamiento = v_alojamiento
          AND fecha_checkin = c_segundo_inicio;
        RETURN v_resultado;
    END;
BEGIN
    SELECT h.id_habitacion, h.id_alojamiento INTO v_habitacion, v_alojamiento
    FROM v_e3_habitaciones h
    WHERE NOT EXISTS (
        SELECT 1 FROM reserva_habitacion rh JOIN reserva r ON r.id_reserva = rh.id_reserva
        WHERE rh.id_habitacion = h.id_habitacion AND r.estado <> 'CANCELADA'
          AND r.fecha_checkin < c_segundo_inicio + 1 AND r.fecha_checkout > c_inicio
    )
    ORDER BY h.id_habitacion FETCH FIRST 1 ROW ONLY;
    SELECT MIN(id_cliente) INTO v_cliente FROM v_e3_clientes;

    v_habitaciones.EXTEND;
    v_habitaciones(1).id_habitacion := v_habitacion;
    v_habitaciones(1).personas_hospedadas := 1;
    v_monto := pkg_turismouq.fn_valor_estadia(v_habitacion, c_inicio, c_inicio + 1);
    sp_reserva_con_pago(v_cliente, v_alojamiento, c_inicio, c_inicio + 1,
        v_habitaciones, v_servicios, v_monto, 'EFECTIVO', v_reserva, v_pago, v_total);
    DBMS_OUTPUT.PUT_LINE('Primera reserva y pago listos en esta transaccion: ' || v_reserva || ' / ' || v_pago);

    v_antes := cantidad_reservas_segunda();
    v_monto := pkg_turismouq.fn_valor_estadia(v_habitacion, c_segundo_inicio, c_segundo_inicio + 1);
    BEGIN
        sp_reserva_con_pago(v_cliente, v_alojamiento, c_segundo_inicio, c_segundo_inicio + 1,
            v_habitaciones, v_servicios, v_monto + 1, 'EFECTIVO',
            v_descartado, v_otro_pago, v_otro_total);
        RAISE_APPLICATION_ERROR(-20420, 'Se esperaba un rechazo del monto.');
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLCODE <> -20401 THEN RAISE; END IF;
            DBMS_OUTPUT.PUT_LINE('Segundo intento rechazado: ' || SQLERRM);
    END;

    SELECT COUNT(*) INTO v_cantidad
    FROM reserva r JOIN pago p ON p.id_reserva = r.id_reserva
    WHERE r.id_reserva = v_reserva AND p.id_pago = v_pago AND p.monto = v_total
      AND r.estado = 'CONFIRMADA' AND p.estado_pago = 'APROBADO';
    IF v_cantidad <> 1 OR cantidad_reservas_segunda() <> v_antes THEN
        RAISE_APPLICATION_ERROR(-20421, 'El rollback parcial no preservo solo el primer intento.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('Rollback parcial verificado: se conservo el primer trabajo y no quedo la segunda reserva.');
    ROLLBACK;
    DBMS_OUTPUT.PUT_LINE('La demostracion revirtio el primer trabajo antes de salir.');
END;
/
