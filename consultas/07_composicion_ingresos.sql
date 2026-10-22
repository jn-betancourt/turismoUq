-- CONSULTA 7: UNPIVOT del ingreso contratado no cancelado por municipio/anio.
-- Anio del check-in; hospedaje y servicios conservan los importes contratados.
-- Total cero produce porcentaje NULL, nunca una division por cero.
SELECT municipio,
       anio,
       concepto,
       valor,
       ROUND(
           100 * valor / NULLIF(SUM(valor) OVER (PARTITION BY id_municipio, anio), 0),
           2
       ) AS pct_del_total
FROM (
    SELECT m.id_municipio,
           m.nombre AS municipio,
           EXTRACT(YEAR FROM i.fecha_checkin) AS anio,
           SUM(i.ingreso_hospedaje) AS hospedaje,
           SUM(i.ingreso_servicios) AS servicios
    FROM vw_ingreso_reserva i
    JOIN alojamiento a ON a.id_alojamiento = i.id_alojamiento
    JOIN municipio m ON m.id_municipio = a.id_municipio
    GROUP BY m.id_municipio, m.nombre, EXTRACT(YEAR FROM i.fecha_checkin)
)
UNPIVOT (
    valor FOR concepto IN (
        hospedaje AS 'HOSPEDAJE',
        servicios AS 'SERVICIOS'
    )
)
ORDER BY municipio, anio, concepto;
