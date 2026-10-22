-- CONSULTA 1: ocupacion reservada por municipio/mes, sobre inventario bruto.
-- Periodo mostrado: horizonte completo declarado por vw_calendario_mes.
-- Para recortar, sustituir SOLO el periodo_informe por limites mensuales.
-- Los meses fuera del horizonte no se inventan como ceros; inventario cero
-- produce porcentaje NULL. El porcentaje municipal no promedia porcentajes.
WITH periodo_informe AS (
    SELECT MIN(mes) AS fecha_inicio, MAX(mes_siguiente) AS fecha_fin_exclusiva
    FROM vw_calendario_mes
),
municipio_mes AS (
    SELECT m.nombre AS municipio,
           c.mes,
           NVL(SUM(o.noches_ocupadas), 0) AS noches_ocupadas,
           NVL(SUM(o.noches_disponibles), 0) AS noches_disponibles
    FROM municipio m
    CROSS JOIN vw_calendario_mes c
    LEFT JOIN vw_ocupacion_mensual_base o
      ON o.id_municipio = m.id_municipio AND o.mes = c.mes
    CROSS JOIN periodo_informe p
    WHERE c.mes >= p.fecha_inicio AND c.mes < p.fecha_fin_exclusiva
    GROUP BY m.id_municipio, m.nombre, c.mes
),
base AS (
    SELECT municipio,
           EXTRACT(YEAR FROM mes) AS anio,
           EXTRACT(MONTH FROM mes) AS mes_num,
           ROUND(100 * noches_ocupadas / NULLIF(noches_disponibles, 0), 1)
               AS pct_ocupacion_bruta
    FROM municipio_mes
)
SELECT *
FROM base
PIVOT (
    MAX(pct_ocupacion_bruta)
    FOR mes_num IN (
        1 AS ene, 2 AS feb, 3 AS mar, 4 AS abr, 5 AS may, 6 AS jun,
        7 AS jul, 8 AS ago, 9 AS sep, 10 AS oct, 11 AS nov, 12 AS dic
    )
)
ORDER BY municipio, anio;
