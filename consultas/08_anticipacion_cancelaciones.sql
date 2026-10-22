-- CONSULTA 8 LIBRE: segun temporada del check-in, con cuanta anticipacion
-- reservan los turistas, cuanto se quedan y que tanto cancelan?
-- Uso: orientar antelacion de campanas y analizar cancelaciones.
-- Incluye CANCELADA a proposito. El conjunto debe tener cobertura unica de
-- temporadas: el verificador detecta huecos/solapes antes de certificarlo.
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
       ROUND(AVG(r.fecha_checkout - r.fecha_checkin), 1) AS noches_promedio
FROM reserva r
JOIN temporada t
  ON r.fecha_checkin >= t.fecha_inicio
 AND r.fecha_checkin < t.fecha_fin + 1
GROUP BY t.tipo_temporada
ORDER BY DECODE(t.tipo_temporada, 'ALTA', 1, 'MEDIA', 2, 'BAJA', 3);
