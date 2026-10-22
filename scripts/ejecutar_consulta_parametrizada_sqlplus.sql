-- Lanzador SQL*Plus / SQLcl. Cambiar estos dos valores, no el SELECT.
-- Iniciar SQL*Plus / SQLcl con el directorio de trabajo en la raiz del repo.
-- @consultas/ usa esa raiz y evita el recorrido .. de @@ en SQL*Plus Windows.
-- Los binds se inicializan y validan en la misma conexion que el informe.
SET DEFINE OFF
SET VERIFY OFF
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';

VARIABLE fecha_ini VARCHAR2(10)
VARIABLE fecha_fin VARCHAR2(10)

BEGIN
    :fecha_ini := '2025-06-01';
    :fecha_fin := '2025-07-31';
END;
/
@@validar_parametros_consulta.sql

PRINT fecha_ini
PRINT fecha_fin

@consultas/05_consulta_parametrizada.sql
