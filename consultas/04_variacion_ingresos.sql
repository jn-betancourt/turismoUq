-- CONSULTA 4: ingreso contratado asignado al mes del check-in (LAG).
-- Periodo mostrado: horizonte completo de vw_calendario_mes.
-- Para otro periodo, modificar SOLO periodo_informe: LAG se calcula sobre
-- el calendario completo ANTES del filtro de presentacion.
-- Mes conocido sin reservas = 0; fuera del historial no se supone ingreso 0.
WITH periodo_informe AS (
    SELECT MIN(mes) AS fecha_inicio, MAX(mes_siguiente) AS fecha_fin_exclusiva
    FROM vw_calendario_mes
),
ingreso_mensual AS (
    SELECT TRUNC(fecha_checkin, 'MM') AS mes, SUM(ingreso_total) AS ingreso
    FROM vw_ingreso_reserva
    GROUP BY TRUNC(fecha_checkin, 'MM')
),
mensual AS (
    SELECT c.mes, NVL(i.ingreso, 0) AS ingreso
    FROM vw_calendario_mes c
    LEFT JOIN ingreso_mensual i ON i.mes = c.mes
),
con_lag AS (
    SELECT mes,
           ingreso,
           LAG(ingreso, 1) OVER (ORDER BY mes) AS ingreso_mes_anterior,
           LAG(ingreso, 12) OVER (ORDER BY mes) AS ingreso_mismo_mes_anio_ant
    FROM mensual
)
SELECT TO_CHAR(l.mes, 'YYYY-MM') AS mes,
       l.ingreso,
       l.ingreso_mes_anterior,
       l.ingreso_mismo_mes_anio_ant,
       l.ingreso - l.ingreso_mes_anterior AS variacion_absoluta,
       ROUND(
           100 * (l.ingreso - l.ingreso_mes_anterior)
           / NULLIF(l.ingreso_mes_anterior, 0), 2
       ) AS variacion_pct,
       ROUND(
           100 * (l.ingreso - l.ingreso_mismo_mes_anio_ant)
           / NULLIF(l.ingreso_mismo_mes_anio_ant, 0), 2
       ) AS variacion_anual_pct
FROM con_lag l
CROSS JOIN periodo_informe p
WHERE l.mes >= p.fecha_inicio AND l.mes < p.fecha_fin_exclusiva
ORDER BY l.mes;
