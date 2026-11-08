SELECT id_reserva, id_alojamiento, fecha_checkout, valor_total
FROM reserva
WHERE estado = 'FINALIZADA'
  AND fecha_checkout >= :inicio AND fecha_checkout < :fin
ORDER BY fecha_checkout, id_reserva
