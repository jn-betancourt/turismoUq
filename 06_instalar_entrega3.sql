-- Ejecutar como propietario E2, en la raiz del repositorio, sin DML pendiente.
SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

@@scripts/verificar_entrega2.sql
@@migraciones/003_solicitud_pago.sql
@@plsql/01_pkg_turismouq.pks
@@plsql/02_pkg_turismouq.pkb
@@scripts/verificar_entrega2.sql
@@plsql/06_sp_reserva_con_pago.sql
@@scripts/vistas_entrega3.sql
@@plsql/07_trg_solicitar_reserva_pago.sql

DECLARE
    v_validos PLS_INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_validos FROM user_objects
    WHERE status = 'VALID' AND object_name IN (
        'PKG_RESERVA_PAGO_INTERNO', 'SP_RESERVA_CON_PAGO', 'TRG_SOLICITAR_RESERVA_PAGO',
        'V_E3_ALOJAMIENTOS', 'V_E3_HABITACIONES', 'V_E3_CLIENTES',
        'V_E3_TARIFAS_COTIZACION', 'V_E3_SOLICITUD_PAGO', 'V_E3_ADMIN_TARIFAS',
        'V_E3_GERENCIA_MENSUAL', 'V_E3_AUDITORIA_TARIFA'
    );
    IF v_validos <> 12 THEN
        RAISE_APPLICATION_ERROR(-20400, 'Consulte USER_ERRORS: hay objetos E3 invalidos.');
    END IF;
END;
/
