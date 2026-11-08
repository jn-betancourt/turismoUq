-- Opcional: cuentas locales de demostracion. Ejecutar como SYS en XEPDB1.
-- @09_preparar_cuentas_entrega3.sql TURISMOUQ_E3
SET DEFINE ON
SET VERIFY OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

COLUMN e3_owner_name NEW_VALUE e3_owner NOPRINT
SELECT UPPER(DBMS_ASSERT.SIMPLE_SQL_NAME('&1')) AS e3_owner_name FROM dual;

DECLARE
    v_cantidad PLS_INTEGER;
BEGIN
    IF SYS_CONTEXT('USERENV', 'CON_NAME') <> 'XEPDB1'
       OR SYS_CONTEXT('USERENV', 'SESSION_USER') <> 'SYS'
       OR NOT REGEXP_LIKE('&&e3_owner', '^TURISMOUQ_[A-Z0-9_]{1,20}$') THEN
        RAISE_APPLICATION_ERROR(-20410, 'Use SYS en XEPDB1 y un propietario TURISMOUQ_*.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM dba_users
    WHERE username IN ('&&e3_owner._USR_RECEP', '&&e3_owner._USR_ADMIN',
                       '&&e3_owner._USR_GERENTE', '&&e3_owner._USR_AUDITOR');
    IF v_cantidad <> 0 THEN
        RAISE_APPLICATION_ERROR(-20413, 'Ya existe alguna cuenta de demostracion; no se modifico.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM dba_roles
    WHERE role IN ('&&e3_owner._RECEPCION', '&&e3_owner._ADMIN_ALOJAMIENTO',
                   '&&e3_owner._GERENTE', '&&e3_owner._AUDITOR');
    IF v_cantidad <> 4 THEN
        RAISE_APPLICATION_ERROR(-20414, 'Primero configure los cuatro roles de Entrega 3.');
    END IF;
END;
/

CREATE USER &&e3_owner._USR_RECEP NO AUTHENTICATION PROFILE &&e3_owner._PERFIL;
CREATE USER &&e3_owner._USR_ADMIN NO AUTHENTICATION PROFILE &&e3_owner._PERFIL;
CREATE USER &&e3_owner._USR_GERENTE NO AUTHENTICATION PROFILE &&e3_owner._PERFIL;
CREATE USER &&e3_owner._USR_AUDITOR NO AUTHENTICATION PROFILE &&e3_owner._PERFIL;

GRANT CREATE SESSION, &&e3_owner._RECEPCION TO &&e3_owner._USR_RECEP;
GRANT CREATE SESSION, &&e3_owner._ADMIN_ALOJAMIENTO TO &&e3_owner._USR_ADMIN;
GRANT CREATE SESSION, &&e3_owner._GERENTE TO &&e3_owner._USR_GERENTE;
GRANT CREATE SESSION, &&e3_owner._AUDITOR TO &&e3_owner._USR_AUDITOR;

UNDEFINE e3_owner
UNDEFINE 1
SET DEFINE OFF
