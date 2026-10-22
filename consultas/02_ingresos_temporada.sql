-- CONSULTA 2: hospedaje contratado por municipio, tipo y temporada aplicada.
-- Poblacion: todo el historial no cancelado. No incluye servicios.
-- SIN DESGLOSE HISTORICO conserva el importe sin inferir su distribucion.
-- Si importe_sin_desglose > 0 o detalles_sin_desglose > 0, el analisis por
-- temporada es parcial. Las filas verificadas se certifican con el verificador.
SELECT CASE
           WHEN GROUPING(m.nombre) = 1 THEN '*** TOTAL GENERAL ***'
           ELSE m.nombre
       END AS municipio,
       CASE
           WHEN GROUPING(m.nombre) = 1 THEN NULL
           WHEN GROUPING(tal.nombre) = 1 THEN '** Subtotal municipio **'
           ELSE tal.nombre
       END AS tipo_alojamiento,
       CASE
           WHEN GROUPING(tal.nombre) = 1 THEN NULL
           WHEN GROUPING(i.tipo_temporada_aplicado) = 1 THEN '* Subtotal tipo *'
           ELSE i.tipo_temporada_aplicado
       END AS temporada,
       GROUPING_ID(m.nombre, tal.nombre, i.tipo_temporada_aplicado)
           AS nivel_agregacion,
       SUM(i.importe_hospedaje) AS ingreso_hospedaje,
       SUM(CASE WHEN i.desglose_verificado = 'NO' THEN i.importe_hospedaje ELSE 0 END)
           AS importe_sin_desglose,
       SUM(CASE WHEN i.desglose_verificado = 'NO' THEN 1 ELSE 0 END)
           AS detalles_sin_desglose
FROM vw_ingreso_hospedaje_temporada i
JOIN municipio m ON m.id_municipio = i.id_municipio
JOIN tipo_alojamiento tal ON tal.id_tipo_alojamiento = i.id_tipo_alojamiento
GROUP BY ROLLUP(m.nombre, tal.nombre, i.tipo_temporada_aplicado)
ORDER BY m.nombre NULLS LAST, tal.nombre NULLS LAST,
         i.tipo_temporada_aplicado NULLS LAST;
