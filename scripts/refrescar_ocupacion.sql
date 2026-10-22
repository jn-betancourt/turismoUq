-- Refresco manual de la MV: ejecutar despues de cambiar fuentes y antes
-- de producir evidencia. El refresco es una operacion de escritura y puede
-- confirmar transacciones: usar una sesion sin trabajo pendiente.
SET DEFINE OFF
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';

BEGIN
    DBMS_MVIEW.REFRESH(
        list => 'MV_OCUPACION_MENSUAL',
        method => 'C',
        atomic_refresh => TRUE
    );
END;
/

SELECT mview_name, refresh_mode, refresh_method, last_refresh_type,
       last_refresh_date, staleness, compile_state
FROM user_mviews
WHERE mview_name = 'MV_OCUPACION_MENSUAL';
