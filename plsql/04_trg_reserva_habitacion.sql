-- Recoge OLD/NEW por fila; la consulta del conjunto ocurre cuando ya no muta.
-- El helper bloquea cabeceras y habitaciones ordenadas antes de releerlas.
SET DEFINE OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE TRIGGER trg_reserva_habitacion
FOR INSERT OR UPDATE OF id_reserva, id_habitacion, personas_hospedadas
ON reserva_habitacion
COMPOUND TRIGGER
    v_reservas pkg_turismouq.lista_identificadores := pkg_turismouq.lista_identificadores();
    v_habitaciones pkg_turismouq.lista_identificadores := pkg_turismouq.lista_identificadores();

    AFTER EACH ROW IS
    BEGIN
        IF UPDATING THEN
            v_reservas.EXTEND;
            v_reservas(v_reservas.LAST) := :OLD.id_reserva;
            v_habitaciones.EXTEND;
            v_habitaciones(v_habitaciones.LAST) := :OLD.id_habitacion;
        END IF;
        v_reservas.EXTEND;
        v_reservas(v_reservas.LAST) := :NEW.id_reserva;
        v_habitaciones.EXTEND;
        v_habitaciones(v_habitaciones.LAST) := :NEW.id_habitacion;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        IF v_reservas.COUNT > 0 THEN
            pkg_turismouq.validar_reservas(v_reservas, v_habitaciones);
        END IF;
    END AFTER STATEMENT;
END trg_reserva_habitacion;
/
