-- CONSULTA 3: los tres puestos de mayor ingreso contratado por municipio.
-- Poblacion: todo el historial no cancelado, hospedaje y servicios.
-- RANK conserva empates; un empate en el tercer puesto puede dar mas de 3 filas.
WITH ingreso_alojamiento AS (
    SELECT m.id_municipio,
           m.nombre AS municipio,
           a.id_alojamiento,
           a.nombre AS alojamiento,
           COUNT(*) AS num_reservas,
           SUM(i.ingreso_total) AS ingreso_total
    FROM vw_ingreso_reserva i
    JOIN alojamiento a ON a.id_alojamiento = i.id_alojamiento
    JOIN municipio m ON m.id_municipio = a.id_municipio
    GROUP BY m.id_municipio, m.nombre, a.id_alojamiento, a.nombre
),
ranking AS (
    SELECT ia.*,
           RANK() OVER (
               PARTITION BY id_municipio ORDER BY ingreso_total DESC
           ) AS puesto
    FROM ingreso_alojamiento ia
)
SELECT municipio, puesto, alojamiento, num_reservas, ingreso_total
FROM ranking
WHERE puesto <= 3
ORDER BY municipio, puesto, id_alojamiento;
