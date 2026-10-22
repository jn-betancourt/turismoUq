-- =============================================================================
-- TURISMOUQ - ENTREGA 1 - OCHO CONSULTAS (LECTURA)
-- Motor: Oracle Database XE 21c. Lanzador para SQL*Plus / SQLcl.
-- Iniciar el cliente con el directorio de trabajo en la raiz del repositorio.
-- Las rutas @consultas/ del adaptador de consulta 5 parten de esa raiz.
-- Preparar una sola vez con scripts/preparar_analitica.sql y refrescar la MV
-- mediante scripts/refrescar_ocupacion.sql antes de producir evidencia.
-- Este archivo no crea, elimina ni refresca objetos.
-- En otro cliente, abrir cada SELECT de consultas/ y proporcionar los binds
-- de la consulta 5 mediante su mecanismo de parametros.
-- Metricas: reservas no CANCELADAS, ingreso contratado al check-in e
-- inventario bruto actual; no representan pagos ni disponibilidad historica.
-- =============================================================================
SET DEFINE OFF
SET VERIFY OFF
SET FEEDBACK ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';

PROMPT Consulta 1 - Ocupacion reservada sobre inventario bruto (PIVOT)
@@consultas/01_ocupacion_municipio_mes.sql
PROMPT Consulta 2 - Hospedaje contratado por temporada (ROLLUP / GROUPING)
@@consultas/02_ingresos_temporada.sql
PROMPT Consulta 3 - Mayores ingresos contratados por municipio (RANK)
@@consultas/03_top_alojamientos.sql
PROMPT Consulta 4 - Variacion mensual por mes del check-in (LAG)
@@consultas/04_variacion_ingresos.sql
PROMPT Consulta 5 - Rango de check-in con variables de enlace
@@scripts/ejecutar_consulta_parametrizada_sqlplus.sql
PROMPT Consulta 6 - Alojamientos con ocupacion inferior al 30 por ciento
@@consultas/06_ocupacion_materializada.sql
PROMPT Consulta 7 - Composicion de ingreso contratado (UNPIVOT)
@@consultas/07_composicion_ingresos.sql
PROMPT Consulta 8 - Anticipacion, duracion y cancelaciones por temporada
@@consultas/08_anticipacion_cancelaciones.sql
