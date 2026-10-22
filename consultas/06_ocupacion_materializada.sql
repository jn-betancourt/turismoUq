-- CONSULTA 6: ejemplo gerencial sobre la MV, incluidos alojamientos con 0%.
-- Periodo explicito: diciembre de 2025; cambiar este CTE para otro mes/rango.
-- COMPLETE ON DEMAND: refrescar antes mediante scripts/refrescar_ocupacion.sql.
-- Porcentaje sobre inventario bruto actual; no disponibilidad en tiempo real.
WITH periodo_informe AS (
    SELECT DATE '2025-12-01' AS fecha_inicio,
           DATE '2026-01-01' AS fecha_fin_exclusiva
    FROM dual
)
SELECT m.nombre AS municipio,
       a.nombre AS alojamiento,
       TO_CHAR(mv.mes, 'YYYY-MM') AS mes,
       mv.noches_ocupadas,
       mv.noches_disponibles AS capacidad_noches_bruta,
       ROUND(mv.pct_ocupacion, 2) AS pct_ocupacion_bruta
FROM mv_ocupacion_mensual mv
JOIN alojamiento a ON a.id_alojamiento = mv.id_alojamiento
JOIN municipio m ON m.id_municipio = mv.id_municipio
CROSS JOIN periodo_informe p
WHERE mv.mes >= p.fecha_inicio AND mv.mes < p.fecha_fin_exclusiva
  AND mv.pct_ocupacion < 30
ORDER BY mv.pct_ocupacion, m.nombre, a.id_alojamiento, mv.mes;
