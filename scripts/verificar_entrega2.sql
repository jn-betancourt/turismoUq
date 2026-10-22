-- Acredita instalacion/compilacion; las pruebas funcionales son independientes.
SET DEFINE OFF
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('PKG_TURISMOUQ', 'TRG_AUDITAR_TARIFA',
               'TRG_RESERVA_HABITACION', 'TRG_RESERVA')
ORDER BY name, type, sequence;

DECLARE
    v_cantidad PLS_INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_cantidad FROM user_objects
    WHERE ((object_name = 'PKG_TURISMOUQ' AND object_type IN ('PACKAGE', 'PACKAGE BODY'))
       OR (object_name IN ('TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA')
           AND object_type = 'TRIGGER')) AND status = 'VALID';
    IF v_cantidad <> 5 THEN
        RAISE_APPLICATION_ERROR(-20403, 'Faltan objetos PL/SQL validos: esperados 5.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_errors
    WHERE name IN ('PKG_TURISMOUQ', 'TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA')
      AND attribute = 'ERROR';
    IF v_cantidad <> 0 THEN
        RAISE_APPLICATION_ERROR(-20404, 'Existen errores de compilacion PL/SQL.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_triggers
    WHERE trigger_name IN ('TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA')
      AND status = 'ENABLED' AND trigger_type = 'COMPOUND';
    IF v_cantidad <> 3 THEN
        RAISE_APPLICATION_ERROR(-20405, 'Se requieren los tres triggers compuestos habilitados.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('INSTALACION PL/SQL E2: APROBADA.');
    DBMS_OUTPUT.PUT_LINE('La compilacion no sustituye las pruebas funcionales/concurrentes.');
END;
/

SELECT object_name, object_type, status FROM user_objects
WHERE object_name IN ('PKG_TURISMOUQ', 'TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA')
ORDER BY object_name, object_type;
