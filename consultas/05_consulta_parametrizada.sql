-- CONSULTA 5 CANONICA: solo SELECT con variables de enlace de texto.
-- Validar antes con scripts/validar_parametros_consulta.sql en la MISMA sesion.
-- :fecha_ini y :fecha_fin: VARCHAR2, formato exacto YYYY-MM-DD; dias incluidos.
-- SQL*Plus / SQLcl: usar scripts/ejecutar_consulta_parametrizada_sqlplus.sql.
-- GUI: proporcionar ambos valores sin comillas adicionales en el dialogo binds.
SELECT m.nombre AS municipio,
       a.nombre AS alojamiento,
       COUNT(*) AS num_reservas,
       SUM(i.ingreso_total) AS ingreso_total,
       ROUND(AVG(i.ingreso_total), 2) AS ticket_promedio,
       ROUND(AVG(i.fecha_checkout - i.fecha_checkin), 1) AS noches_promedio
FROM vw_ingreso_reserva i
JOIN alojamiento a ON a.id_alojamiento = i.id_alojamiento
JOIN municipio m ON m.id_municipio = a.id_municipio
WHERE i.fecha_checkin >= TO_DATE(:fecha_ini, 'FXYYYY-MM-DD')
  AND i.fecha_checkin < TO_DATE(:fecha_fin, 'FXYYYY-MM-DD') + 1
GROUP BY a.id_alojamiento, m.nombre, a.nombre
ORDER BY ingreso_total DESC, a.id_alojamiento;
