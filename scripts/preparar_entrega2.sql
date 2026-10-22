-- Preflight del propietario. Los grants administrativos se documentan aparte.
-- No crea usuarios, no cambia claves y no modifica tablas.
SET DEFINE OFF
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

DECLARE
    v_cantidad PLS_INTEGER;
BEGIN
    IF SYS_CONTEXT('USERENV', 'SESSION_USER') IN ('SYS', 'SYSTEM') THEN
        RAISE_APPLICATION_ERROR(-20400, 'Instale la capa PL/SQL como propietario del proyecto.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_sys_privs
    WHERE privilege IN ('CREATE PROCEDURE', 'CREATE TRIGGER');
    IF v_cantidad <> 2 THEN
        RAISE_APPLICATION_ERROR(-20401,
            'Faltan grants directos CREATE PROCEDURE / CREATE TRIGGER al propietario.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_tables
    WHERE table_name IN (
        'USUARIO_SISTEMA', 'PROPIETARIO', 'CLIENTE', 'MUNICIPIO',
        'TIPO_ALOJAMIENTO', 'ALOJAMIENTO', 'TIPO_HABITACION', 'HABITACION',
        'COMODIDAD', 'ALOJAMIENTO_COMODIDAD', 'TEMPORADA', 'TARIFA',
        'AUDITORIA_TARIFA', 'RESERVA', 'RESERVA_HABITACION', 'PAGO',
        'SERVICIO', 'RESERVA_SERVICIO', 'RESENA', 'LIQUIDACION_MENSUAL',
        'HISTORICO_RESERVA', 'RESERVA_HABITACION_TARIFA_APLICADA'
    );
    IF v_cantidad <> 22 THEN
        RAISE_APPLICATION_ERROR(-20402, 'Se requieren las 22 tablas del modelo de Entrega 1.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('PREFLIGHT E2: propietario y privilegios comprobados.');
END;
/
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
