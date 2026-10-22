-- =============================================================================
-- PROYECTO INTEGRADOR BDII - TURISMOUQ
-- Entrega 1: Consultas de analisis (8 consultas)
-- Motor: Oracle Database XE 21c
-- =============================================================================
--
-- PRERREQUISITOS
--   * Haber ejecutado 01_ddl.sql y 02_carga.sql.
--   * El usuario del proyecto necesita (conceder como SYSTEM):
--       GRANT CREATE VIEW TO <USUARIO_PROYECTO>;
--       GRANT CREATE MATERIALIZED VIEW TO <USUARIO_PROYECTO>;
--   * Ejecutar con "Run Script" (F5) en SQL Developer o en SQL*Plus / SQLcl,
--     porque la consulta 5 usa comandos VARIABLE / EXEC.
--
-- SUPUESTOS DEL MODELO
--   * fecha_checkin y fecha_checkout se guardan sin hora (TRUNC).
--   * Las temporadas no se solapan y cubren todo el calendario 2024-2026.
--   * Cada reserva tiene id_alojamiento (se recomienda dejarlo NOT NULL).
--   * Las reservas CANCELADAS no cuentan como ocupacion ni como ingreso.
-- =============================================================================

SET DEFINE OFF;

-- =============================================================================
-- VISTAS DE APOYO
-- Centralizan dos definiciones que usan varias consultas, para que todas
-- midan "ocupacion" e "ingreso" de la misma manera.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- vw_noche_reservada: una fila por cada noche ocupada de cada habitacion.
-- Es la base de la ocupacion y permite que una estadia que atraviesa dos
-- temporadas se reparta noche a noche con la tarifa que corresponde.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_noche_reservada AS
WITH dias AS (
    SELECT LEVEL - 1 AS n
    FROM   dual
    CONNECT BY LEVEL <= 366
)
SELECT r.id_reserva,
       r.id_cliente,
       rh.id_habitacion,
       h.id_alojamiento,
       a.id_municipio,
       a.id_tipo_alojamiento,
       TRUNC(r.fecha_checkin) + d.n          AS fecha_noche,
       t.id_temporada,
       NVL(t.tipo_temporada, 'SIN TEMPORADA') AS tipo_temporada,
       ta.precio_noche
FROM   reserva r
JOIN   reserva_habitacion rh ON rh.id_reserva     = r.id_reserva
JOIN   habitacion h          ON h.id_habitacion   = rh.id_habitacion
JOIN   alojamiento a         ON a.id_alojamiento  = h.id_alojamiento
JOIN   dias d
       ON d.n < TRUNC(r.fecha_checkout) - TRUNC(r.fecha_checkin)
LEFT JOIN temporada t
       ON TRUNC(r.fecha_checkin) + d.n BETWEEN t.fecha_inicio AND t.fecha_fin
LEFT JOIN tarifa ta
       ON ta.id_habitacion = rh.id_habitacion
      AND ta.id_temporada  = t.id_temporada
WHERE  r.estado <> 'CANCELADA';

COMMENT ON TABLE vw_noche_reservada IS
    'Una fila por noche ocupada y habitacion, con su temporada y tarifa.';

-- -----------------------------------------------------------------------------
-- vw_ingreso_reserva: ingreso de cada reserva (hospedaje + servicios)
-- calculado desde el detalle, sin depender de reserva.valor_total.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_ingreso_reserva AS
SELECT r.id_reserva,
       r.id_cliente,
       r.id_alojamiento,
       r.fecha_reserva,
       r.fecha_checkin,
       r.fecha_checkout,
       r.estado,
       NVL(h.hospedaje, 0)                       AS ingreso_hospedaje,
       NVL(s.servicios, 0)                       AS ingreso_servicios,
       NVL(h.hospedaje, 0) + NVL(s.servicios, 0) AS ingreso_total
FROM   reserva r
LEFT JOIN (
        SELECT id_reserva, SUM(precio_estadia_habitacion) AS hospedaje
        FROM   reserva_habitacion
        GROUP BY id_reserva
       ) h ON h.id_reserva = r.id_reserva
LEFT JOIN (
        SELECT id_reserva, SUM(subtotal) AS servicios
        FROM   reserva_servicio
        GROUP BY id_reserva
       ) s ON s.id_reserva = r.id_reserva
WHERE  r.estado <> 'CANCELADA';

COMMENT ON TABLE vw_ingreso_reserva IS
    'Ingreso por reserva no cancelada: hospedaje + servicios.';


-- =============================================================================
-- CONSULTA 1. OCUPACION POR MUNICIPIO Y MES (PIVOT)
-- Porcentaje de ocupacion = noches ocupadas / noches disponibles del mes.
-- Noches disponibles = habitaciones del municipio x dias del mes.
-- Filas: municipio y anio. Columnas: los 12 meses.
-- =============================================================================
WITH ocupadas AS (
    SELECT id_municipio,
           TRUNC(fecha_noche, 'MM') AS mes,
           COUNT(*)                 AS noches_ocupadas
    FROM   vw_noche_reservada
    GROUP BY id_municipio, TRUNC(fecha_noche, 'MM')
),
habitaciones_municipio AS (
    SELECT a.id_municipio,
           COUNT(*) AS num_habitaciones
    FROM   habitacion h
    JOIN   alojamiento a ON a.id_alojamiento = h.id_alojamiento
    GROUP BY a.id_municipio
),
base AS (
    SELECT m.nombre                   AS municipio,
           EXTRACT(YEAR  FROM o.mes)  AS anio,
           EXTRACT(MONTH FROM o.mes)  AS mes_num,
           ROUND(
               100 * o.noches_ocupadas
               / (hm.num_habitaciones * (ADD_MONTHS(o.mes, 1) - o.mes)),
               1
           )                          AS pct_ocupacion
    FROM   ocupadas o
    JOIN   habitaciones_municipio hm ON hm.id_municipio = o.id_municipio
    JOIN   municipio m               ON m.id_municipio  = o.id_municipio
)
SELECT *
FROM   base
PIVOT (
    MAX(pct_ocupacion)
    FOR mes_num IN (
        1 AS ene, 2 AS feb, 3 AS mar, 4 AS abr,  5 AS may,  6 AS jun,
        7 AS jul, 8 AS ago, 9 AS sep, 10 AS oct, 11 AS nov, 12 AS dic
    )
)
ORDER BY municipio, anio;


-- =============================================================================
-- CONSULTA 2. INGRESOS POR MUNICIPIO, TIPO DE ALOJAMIENTO Y TEMPORADA
--             (ROLLUP + GROUPING)
-- El ingreso de hospedaje se calcula noche a noche con la tarifa vigente, asi
-- una estadia que cruza temporada ALTA y MEDIA se reparte correctamente.
-- GROUPING() identifica las filas de subtotal y total general.
-- =============================================================================
SELECT CASE
           WHEN GROUPING(m.nombre) = 1 THEN '*** TOTAL GENERAL ***'
           ELSE m.nombre
       END AS municipio,
       CASE
           WHEN GROUPING(m.nombre)   = 1 THEN NULL
           WHEN GROUPING(tal.nombre) = 1 THEN '** Subtotal municipio **'
           ELSE tal.nombre
       END AS tipo_alojamiento,
       CASE
           WHEN GROUPING(tal.nombre)       = 1 THEN NULL
           WHEN GROUPING(n.tipo_temporada) = 1 THEN '* Subtotal tipo *'
           ELSE n.tipo_temporada
       END AS temporada,
       GROUPING_ID(m.nombre, tal.nombre, n.tipo_temporada) AS nivel_agregacion,
       COUNT(*)                                            AS noches_vendidas,
       SUM(NVL(n.precio_noche, 0))                         AS ingreso_hospedaje
FROM   vw_noche_reservada n
JOIN   municipio m          ON m.id_municipio          = n.id_municipio
JOIN   tipo_alojamiento tal ON tal.id_tipo_alojamiento = n.id_tipo_alojamiento
GROUP BY ROLLUP (m.nombre, tal.nombre, n.tipo_temporada)
ORDER BY m.nombre NULLS LAST,
         tal.nombre NULLS LAST,
         n.tipo_temporada NULLS LAST;


-- =============================================================================
-- CONSULTA 3. TOP 3 ALOJAMIENTOS DE MAYOR INGRESO POR MUNICIPIO
--             (RANK con PARTITION BY)
-- RANK respeta empates: si dos alojamientos empatan en el 3er lugar, ambos
-- aparecen (con DENSE_RANK o ROW_NUMBER el resultado seria distinto).
-- =============================================================================
WITH ingreso_alojamiento AS (
    SELECT m.nombre             AS municipio,
           a.id_alojamiento,
           a.nombre             AS alojamiento,
           COUNT(*)             AS num_reservas,
           SUM(i.ingreso_total) AS ingreso_total
    FROM   vw_ingreso_reserva i
    JOIN   alojamiento a ON a.id_alojamiento = i.id_alojamiento
    JOIN   municipio m   ON m.id_municipio   = a.id_municipio
    GROUP BY m.nombre, a.id_alojamiento, a.nombre
),
ranking AS (
    SELECT ia.*,
           RANK() OVER (
               PARTITION BY municipio
               ORDER BY ingreso_total DESC
           ) AS puesto
    FROM   ingreso_alojamiento ia
)
SELECT municipio, puesto, alojamiento, num_reservas, ingreso_total
FROM   ranking
WHERE  puesto <= 3
ORDER BY municipio, puesto;


-- =============================================================================
-- CONSULTA 4. VARIACION DE INGRESOS MES CONTRA MES (LAG)
-- El ingreso se asigna al mes del check-in.
-- Ademas de la variacion contra el mes anterior, se compara contra el mismo
-- mes del anio anterior (LAG de 12), util porque la demanda es estacional.
-- =============================================================================
WITH mensual AS (
    SELECT TRUNC(fecha_checkin, 'MM') AS mes,
           SUM(ingreso_total)         AS ingreso
    FROM   vw_ingreso_reserva
    GROUP BY TRUNC(fecha_checkin, 'MM')
),
con_lag AS (
    SELECT mes,
           ingreso,
           LAG(ingreso, 1)  OVER (ORDER BY mes) AS ingreso_mes_anterior,
           LAG(ingreso, 12) OVER (ORDER BY mes) AS ingreso_mismo_mes_anio_ant
    FROM   mensual
)
SELECT TO_CHAR(mes, 'YYYY-MM')                     AS mes,
       ingreso,
       ingreso_mes_anterior,
       ingreso - ingreso_mes_anterior              AS variacion_absoluta,
       ROUND(
           100 * (ingreso - ingreso_mes_anterior)
           / NULLIF(ingreso_mes_anterior, 0), 2
       )                                           AS variacion_pct,
       ROUND(
           100 * (ingreso - ingreso_mismo_mes_anio_ant)
           / NULLIF(ingreso_mismo_mes_anio_ant, 0), 2
       )                                           AS variacion_anual_pct
FROM   con_lag
ORDER BY mes;


-- =============================================================================
-- CONSULTA 5. CONSULTA PARAMETRIZADA CON VARIABLES DE ENLACE
-- Pregunta: en un rango de fechas, cuantas reservas, cuanto ingreso y cual es
-- el ticket promedio de cada alojamiento.
-- Las variables de enlace permiten que Oracle reutilice el mismo plan de
-- ejecucion (soft parse) con cualquier rango y evitan inyeccion SQL.
-- SQL*Plus no admite VARIABLE de tipo DATE, por eso se usa VARCHAR2 + TO_DATE.
-- =============================================================================
VARIABLE fecha_ini VARCHAR2(10)
VARIABLE fecha_fin VARCHAR2(10)

EXEC :fecha_ini := '2025-06-01';
EXEC :fecha_fin := '2025-07-31';

SELECT m.nombre                            AS municipio,
       a.nombre                            AS alojamiento,
       COUNT(*)                            AS num_reservas,
       SUM(i.ingreso_total)                AS ingreso_total,
       ROUND(AVG(i.ingreso_total), 2)      AS ticket_promedio,
       ROUND(AVG(i.fecha_checkout - i.fecha_checkin), 1) AS noches_promedio
FROM   vw_ingreso_reserva i
JOIN   alojamiento a ON a.id_alojamiento = i.id_alojamiento
JOIN   municipio m   ON m.id_municipio   = a.id_municipio
WHERE  i.fecha_checkin >= TO_DATE(:fecha_ini, 'YYYY-MM-DD')
AND    i.fecha_checkin <  TO_DATE(:fecha_fin, 'YYYY-MM-DD') + 1
GROUP BY m.nombre, a.nombre
ORDER BY ingreso_total DESC;


-- =============================================================================
-- CONSULTA 6. VISTA MATERIALIZADA DE OCUPACION MENSUAL
--
-- POLITICA DE REFRESCO: COMPLETE, ON DEMAND, programado una vez al dia a las
-- 2:00 a.m. (job al final de esta seccion).
--   * No ON COMMIT: cada reserva, pago o cancelacion tendria que recalcular
--     la vista dentro de su propia transaccion, frenando justo la operacion
--     critica del negocio (reservar).
--   * No FAST: la vista usa una expansion de noches (CONNECT BY) y joins
--     con subconsultas agregadas, que no cumplen las restricciones del
--     refresco rapido; ademas exigiria materialized view logs en varias tablas.
--   * Diario es suficiente: la ocupacion mensual es un indicador gerencial;
--     que tenga hasta un dia de desfase no afecta ninguna decision, y a las
--     2:00 a.m. casi no hay transacciones de reserva.
-- =============================================================================

-- Permite volver a ejecutar el script sin error si la vista ya existe.
BEGIN
    EXECUTE IMMEDIATE 'DROP MATERIALIZED VIEW mv_ocupacion_mensual';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -12003 THEN
            RAISE;
        END IF;
END;
/

CREATE MATERIALIZED VIEW mv_ocupacion_mensual
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT n.id_municipio,
       n.id_alojamiento,
       TRUNC(n.fecha_noche, 'MM') AS mes,
       COUNT(*)                   AS noches_ocupadas,
       h.num_habitaciones
         * (ADD_MONTHS(TRUNC(n.fecha_noche, 'MM'), 1)
            - TRUNC(n.fecha_noche, 'MM')) AS noches_disponibles,
       ROUND(
           100 * COUNT(*)
           / (h.num_habitaciones
              * (ADD_MONTHS(TRUNC(n.fecha_noche, 'MM'), 1)
                 - TRUNC(n.fecha_noche, 'MM'))),
           2
       )                          AS pct_ocupacion
FROM   vw_noche_reservada n
JOIN  (
        SELECT id_alojamiento, COUNT(*) AS num_habitaciones
        FROM   habitacion
        GROUP BY id_alojamiento
      ) h ON h.id_alojamiento = n.id_alojamiento
GROUP BY n.id_municipio,
         n.id_alojamiento,
         TRUNC(n.fecha_noche, 'MM'),
         h.num_habitaciones;

COMMENT ON MATERIALIZED VIEW mv_ocupacion_mensual IS
    'Ocupacion mensual por alojamiento; refresco completo diario 2:00 a.m.';

-- Refresco manual (para la sustentacion o despues de una carga):
--   EXEC DBMS_MVIEW.REFRESH('MV_OCUPACION_MENSUAL', 'C');

-- Programacion del refresco diario. Requiere: GRANT CREATE JOB TO <usuario>;
-- Descomentar una vez concedido el privilegio.
--
-- BEGIN
--     DBMS_SCHEDULER.CREATE_JOB(
--         job_name        => 'JOB_REFRESH_MV_OCUPACION',
--         job_type        => 'PLSQL_BLOCK',
--         job_action      => 'BEGIN DBMS_MVIEW.REFRESH(''MV_OCUPACION_MENSUAL'', ''C''); END;',
--         start_date      => SYSTIMESTAMP,
--         repeat_interval => 'FREQ=DAILY;BYHOUR=2;BYMINUTE=0;BYSECOND=0',
--         enabled         => TRUE,
--         comments        => 'Refresco completo diario de la ocupacion mensual'
--     );
-- END;
-- /

-- Ejemplo de uso: alojamientos con ocupacion menor al 30 % en diciembre 2025.
SELECT m.nombre AS municipio,
       a.nombre AS alojamiento,
       mv.noches_ocupadas,
       mv.noches_disponibles,
       mv.pct_ocupacion
FROM   mv_ocupacion_mensual mv
JOIN   alojamiento a ON a.id_alojamiento = mv.id_alojamiento
JOIN   municipio m   ON m.id_municipio   = mv.id_municipio
WHERE  mv.mes = DATE '2025-12-01'
AND    mv.pct_ocupacion < 30
ORDER BY mv.pct_ocupacion;


-- =============================================================================
-- CONSULTA 7. UNPIVOT
-- Composicion del ingreso por municipio y anio. La subconsulta produce una
-- fila ancha (hospedaje y servicios en columnas separadas) y UNPIVOT la
-- convierte en filas concepto/valor, formato comodo para graficar o para
-- comparar la participacion de cada concepto.
-- =============================================================================
SELECT municipio,
       anio,
       concepto,
       valor,
       ROUND(
           100 * valor / NULLIF(SUM(valor) OVER (PARTITION BY municipio, anio), 0),
           2
       ) AS pct_del_total
FROM (
        SELECT m.nombre                          AS municipio,
               EXTRACT(YEAR FROM i.fecha_checkin) AS anio,
               SUM(i.ingreso_hospedaje)          AS hospedaje,
               SUM(i.ingreso_servicios)          AS servicios
        FROM   vw_ingreso_reserva i
        JOIN   alojamiento a ON a.id_alojamiento = i.id_alojamiento
        JOIN   municipio m   ON m.id_municipio   = a.id_municipio
        GROUP BY m.nombre, EXTRACT(YEAR FROM i.fecha_checkin)
     )
UNPIVOT (
    valor FOR concepto IN (
        hospedaje AS 'HOSPEDAJE',
        servicios AS 'SERVICIOS'
    )
)
ORDER BY municipio, anio, concepto;


-- =============================================================================
-- CONSULTA 8. CONSULTA LIBRE - PREGUNTA DE NEGOCIO
-- Pregunta: segun la temporada, con cuanta anticipacion reservan los turistas,
-- cuanto se quedan y que tanto cancelan?
-- Uso: define cuando lanzar campanas (si en temporada ALTA se reserva con
-- 45 dias de anticipacion, la promocion debe salir antes) y si conviene
-- exigir anticipo en las temporadas con mas cancelaciones.
-- Incluye las reservas CANCELADAS a proposito, por eso usa la tabla reserva.
-- =============================================================================
SELECT t.tipo_temporada,
       COUNT(*) AS total_reservas,
       SUM(CASE WHEN r.estado = 'CANCELADA' THEN 1 ELSE 0 END) AS canceladas,
       ROUND(
           100 * AVG(CASE WHEN r.estado = 'CANCELADA' THEN 1 ELSE 0 END), 2
       ) AS pct_cancelacion,
       ROUND(AVG(TRUNC(r.fecha_checkin) - TRUNC(r.fecha_reserva)), 1)
           AS anticipacion_promedio_dias,
       PERCENTILE_CONT(0.5) WITHIN GROUP (
           ORDER BY TRUNC(r.fecha_checkin) - TRUNC(r.fecha_reserva)
       ) AS anticipacion_mediana_dias,
       ROUND(AVG(r.fecha_checkout - r.fecha_checkin), 1)
           AS noches_promedio
FROM   reserva r
JOIN   temporada t
       ON TRUNC(r.fecha_checkin) BETWEEN t.fecha_inicio AND t.fecha_fin
GROUP BY t.tipo_temporada
ORDER BY DECODE(t.tipo_temporada, 'ALTA', 1, 'MEDIA', 2, 'BAJA', 3);

-- =============================================================================
-- FIN DEL SCRIPT
-- =============================================================================
