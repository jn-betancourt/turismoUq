CREATE OR REPLACE TRIGGER trg_solicitar_reserva_pago
INSTEAD OF INSERT ON v_e3_solicitud_pago
FOR EACH ROW
DECLARE
    v_habitaciones pkg_turismouq.lista_solicitudes_habitacion :=
        pkg_turismouq.lista_solicitudes_habitacion();
    v_servicios pkg_turismouq.lista_solicitudes_servicio :=
        pkg_turismouq.lista_solicitudes_servicio();
    v_id_reserva NUMBER;
    v_id_pago NUMBER;
    v_total NUMBER;
    v_disponible PLS_INTEGER;
BEGIN
    IF :NEW.token_solicitud IS NULL OR UTL_RAW.LENGTH(:NEW.token_solicitud) <> 16 THEN
        RAISE_APPLICATION_ERROR(-20403, 'Se requiere un token de solicitud de 16 bytes.');
    END IF;

    SELECT COUNT(*) INTO v_disponible FROM v_e3_habitaciones
    WHERE id_habitacion = :NEW.id_habitacion AND id_alojamiento = :NEW.id_alojamiento;
    IF v_disponible <> 1 THEN
        RAISE_APPLICATION_ERROR(-20304, 'La habitacion no esta disponible en este alojamiento.');
    END IF;

    v_habitaciones.EXTEND;
    v_habitaciones(1).id_habitacion := :NEW.id_habitacion;
    v_habitaciones(1).personas_hospedadas := :NEW.personas;

    pkg_reserva_pago_interno.registrar(
        :NEW.id_cliente, :NEW.id_alojamiento, :NEW.fecha_checkin, :NEW.fecha_checkout,
        v_habitaciones, v_servicios, :NEW.monto, :NEW.metodo_pago,
        v_id_reserva, v_id_pago, v_total
    );

    INSERT INTO solicitud_pago (usuario_oracle, token_solicitud, id_pago)
    VALUES (SYS_CONTEXT('USERENV', 'SESSION_USER'), :NEW.token_solicitud, v_id_pago);
END;
/
