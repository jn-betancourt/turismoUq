-- Ejecutar como propietario, sin transaccion pendiente. Medir el estado previo primero.
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

CREATE INDEX ix_e3_reserva_aloj_checkin ON reserva (id_alojamiento, fecha_checkin);
CREATE INDEX ix_e3_pago_dia ON pago (TRUNC(fecha_pago));
CREATE INDEX ix_e3_reserva_estado_checkout ON reserva (estado, fecha_checkout);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'RESERVA', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'PAGO', cascade => TRUE);
END;
/
