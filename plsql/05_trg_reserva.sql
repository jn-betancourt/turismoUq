-- Impide introducir un solape cambiando fechas, estado o sede de la cabecera.
-- UPDATE de valor_total no dispara este control ni produce recursion.
SET DEFINE OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE TRIGGER trg_reserva
FOR UPDATE OF fecha_checkin, fecha_checkout, estado, id_alojamiento ON reserva
COMPOUND TRIGGER
    v_reservas pkg_turismouq.lista_identificadores := pkg_turismouq.lista_identificadores();

    AFTER EACH ROW IS
    BEGIN
        v_reservas.EXTEND;
        v_reservas(v_reservas.LAST) := :NEW.id_reserva;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        IF v_reservas.COUNT > 0 THEN
            pkg_turismouq.validar_reservas(v_reservas);
        END IF;
    END AFTER STATEMENT;
END trg_reserva;
/
