-- Entrega 2: ejecutar desde la raiz del repositorio, conectado al propietario.
-- Requiere modelo E1 instalado. El DDL confirma transacciones: sesion sin DML pendiente.
-- No recarga datos ni crea/elimina cuentas. La migracion conserva metadatos legados.
SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE ROLLBACK

@@scripts/preparar_entrega2.sql
@@migraciones/002_soporte_plsql.sql
@@plsql/01_pkg_turismouq.pks
@@plsql/02_pkg_turismouq.pkb
@@plsql/03_trg_auditar_tarifa.sql
@@plsql/04_trg_reserva_habitacion.sql
@@plsql/05_trg_reserva.sql
@@scripts/verificar_entrega2.sql
