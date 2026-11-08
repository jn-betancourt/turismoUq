-- Ejecutar como SYS en XEPDB1: @08_configurar_seguridad_entrega3.sql TURISMOUQ_E3
-- El argumento es el nombre Oracle simple (no entrecomillado) del propietario.
SET DEFINE ON
SET VERIFY OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

COLUMN e3_owner_name NEW_VALUE e3_owner NOPRINT
SELECT UPPER(DBMS_ASSERT.SIMPLE_SQL_NAME('&1')) AS e3_owner_name FROM dual;

DECLARE
    v_disponibles PLS_INTEGER;
BEGIN
    IF SYS_CONTEXT('USERENV', 'CON_NAME') <> 'XEPDB1'
       OR SYS_CONTEXT('USERENV', 'SESSION_USER') <> 'SYS'
       OR NOT REGEXP_LIKE('&&e3_owner', '^TURISMOUQ_[A-Z0-9_]{1,20}$') THEN
        RAISE_APPLICATION_ERROR(-20410, 'Use SYS en XEPDB1 y un propietario TURISMOUQ_*.');
    END IF;
    SELECT COUNT(*) INTO v_disponibles FROM dba_objects
    WHERE owner = '&&e3_owner' AND object_name = 'TRG_SOLICITAR_RESERVA_PAGO' AND status = 'VALID';
    IF v_disponibles <> 1 THEN
        RAISE_APPLICATION_ERROR(-20411, 'Primero instale y verifique la capa de Entrega 3.');
    END IF;
    SELECT COUNT(*) INTO v_disponibles FROM v$parameter
    WHERE name = 'resource_limit' AND UPPER(value) = 'TRUE';
    IF v_disponibles <> 1 THEN
        RAISE_APPLICATION_ERROR(-20412, 'Habilite RESOURCE_LIMIT antes de instalar los roles.');
    END IF;
END;
/

CREATE ROLE &&e3_owner._RECEPCION;
CREATE ROLE &&e3_owner._ADMIN_ALOJAMIENTO;
CREATE ROLE &&e3_owner._GERENTE;
CREATE ROLE &&e3_owner._AUDITOR;

CREATE PROFILE &&e3_owner._PERFIL LIMIT
    SESSIONS_PER_USER 3
    IDLE_TIME 15
    CONNECT_TIME 240
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24;

GRANT SELECT ON &&e3_owner..v_e3_alojamientos TO &&e3_owner._RECEPCION;
GRANT SELECT ON &&e3_owner..v_e3_habitaciones TO &&e3_owner._RECEPCION;
GRANT SELECT ON &&e3_owner..v_e3_clientes TO &&e3_owner._RECEPCION;
GRANT SELECT ON &&e3_owner..v_e3_tarifas_cotizacion TO &&e3_owner._RECEPCION;
GRANT SELECT ON &&e3_owner..v_e3_solicitud_pago TO &&e3_owner._RECEPCION;
GRANT INSERT (token_solicitud, id_cliente, id_alojamiento, fecha_checkin, fecha_checkout,
              id_habitacion, personas, monto, metodo_pago)
    ON &&e3_owner..v_e3_solicitud_pago TO &&e3_owner._RECEPCION;

GRANT SELECT ON &&e3_owner..v_e3_admin_tarifas TO &&e3_owner._ADMIN_ALOJAMIENTO;
GRANT UPDATE (precio_noche) ON &&e3_owner..v_e3_admin_tarifas TO &&e3_owner._ADMIN_ALOJAMIENTO;
GRANT SELECT ON &&e3_owner..v_e3_gerencia_mensual TO &&e3_owner._GERENTE;
GRANT SELECT ON &&e3_owner..v_e3_auditoria_tarifa TO &&e3_owner._AUDITOR;

UNDEFINE e3_owner
UNDEFINE 1
SET DEFINE OFF
