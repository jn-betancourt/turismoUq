-- Captura OLD/NEW por fila y persiste la auditoria al terminar la sentencia.
-- Los eventos comparten ID, actor conectado y timestamp UTC. No hay COMMIT.
SET DEFINE OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE TRIGGER trg_auditar_tarifa
FOR UPDATE OF precio_noche ON tarifa
COMPOUND TRIGGER
    TYPE lista_ids_tarifa IS TABLE OF tarifa.id_tarifa%TYPE INDEX BY PLS_INTEGER;
    TYPE lista_precios IS TABLE OF tarifa.precio_noche%TYPE INDEX BY PLS_INTEGER;
    v_ids lista_ids_tarifa;
    v_anteriores lista_precios;
    v_nuevos lista_precios;
    v_cantidad PLS_INTEGER := 0;
    v_id_sentencia RAW(16);
    v_actor VARCHAR2(128);
    v_fecha_utc TIMESTAMP;

    BEFORE STATEMENT IS
    BEGIN
        v_id_sentencia := SYS_GUID();
        v_actor := SYS_CONTEXT('USERENV', 'SESSION_USER');
        v_fecha_utc := SYS_EXTRACT_UTC(SYSTIMESTAMP);
    END BEFORE STATEMENT;

    AFTER EACH ROW IS
    BEGIN
        IF :OLD.precio_noche <> :NEW.precio_noche THEN
            v_cantidad := v_cantidad + 1;
            v_ids(v_cantidad) := :NEW.id_tarifa;
            v_anteriores(v_cantidad) := :OLD.precio_noche;
            v_nuevos(v_cantidad) := :NEW.precio_noche;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        IF v_cantidad > 0 THEN
            FORALL indice IN 1 .. v_cantidad
                INSERT INTO auditoria_tarifa (
                    id_tarifa, usuario_oracle, fecha_cambio, precio_anterior,
                    precio_nuevo, operacion, id_sentencia
                ) VALUES (
                    v_ids(indice), v_actor, v_fecha_utc, v_anteriores(indice),
                    v_nuevos(indice), 'UPDATE', v_id_sentencia
                );
        END IF;
    END AFTER STATEMENT;
END trg_auditar_tarifa;
/
