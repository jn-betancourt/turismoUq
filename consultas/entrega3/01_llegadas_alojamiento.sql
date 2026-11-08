SELECT id_reserva, fecha_checkin, estado, valor_total
FROM reserva
WHERE id_alojamiento = :alojamiento
  AND fecha_checkin >= :inicio AND fecha_checkin < :fin
ORDER BY fecha_checkin, id_reserva
