CREATE OR REPLACE VIEW v_e3_alojamientos AS
SELECT a.id_alojamiento, a.nombre, m.nombre AS municipio
FROM alojamiento a JOIN municipio m ON m.id_municipio = a.id_municipio
WHERE a.estado = 'ACTIVO'
WITH READ ONLY;

CREATE OR REPLACE VIEW v_e3_habitaciones AS
SELECT h.id_habitacion, h.id_alojamiento, h.numero_habitacion,
       t.nombre AS tipo_habitacion, t.capacidad_estandar AS capacidad
FROM habitacion h JOIN tipo_habitacion t ON t.id_tipo_habitacion = h.id_tipo_habitacion
JOIN alojamiento a ON a.id_alojamiento = h.id_alojamiento
WHERE h.estado = 'DISPONIBLE' AND a.estado = 'ACTIVO'
WITH READ ONLY;

CREATE OR REPLACE VIEW v_e3_clientes AS
SELECT c.id_usuario AS id_cliente, c.numero_documento, u.nombre_completo
FROM cliente c JOIN usuario_sistema u ON u.id_usuario = c.id_usuario
WITH READ ONLY;

CREATE OR REPLACE VIEW v_e3_tarifas_cotizacion AS
SELECT t.id_habitacion, s.fecha_inicio, s.fecha_fin, t.precio_noche
FROM tarifa t JOIN temporada s ON s.id_temporada = t.id_temporada
WITH READ ONLY;

-- El INSERT usa solo las columnas de solicitud. El SELECT expone el comprobante
-- del usuario conectado; no se puede leer el historial de otro recepcionista.
CREATE OR REPLACE VIEW v_e3_solicitud_pago AS
SELECT s.token_solicitud, r.id_cliente, r.id_alojamiento,
       r.fecha_checkin, r.fecha_checkout, CAST(NULL AS NUMBER) AS id_habitacion,
       CAST(NULL AS NUMBER) AS personas, p.monto, p.metodo_pago,
       r.id_reserva, p.id_pago, p.fecha_pago, r.estado AS estado_reserva
FROM solicitud_pago s JOIN pago p ON p.id_pago = s.id_pago
JOIN reserva r ON r.id_reserva = p.id_reserva
WHERE s.usuario_oracle = SYS_CONTEXT('USERENV', 'SESSION_USER');

-- Solo precio_noche es modificable por el rol administrador.
CREATE OR REPLACE VIEW v_e3_admin_tarifas AS
SELECT id_tarifa, id_habitacion, id_temporada, precio_noche
FROM tarifa;

CREATE OR REPLACE VIEW v_e3_gerencia_mensual AS
SELECT TRUNC(r.fecha_checkin, 'MM') AS mes, r.id_alojamiento, a.nombre AS alojamiento,
       COUNT(*) AS reservas, SUM(r.valor_total) AS valor_contratado
FROM reserva r JOIN alojamiento a ON a.id_alojamiento = r.id_alojamiento
WHERE r.estado <> 'CANCELADA'
GROUP BY TRUNC(r.fecha_checkin, 'MM'), r.id_alojamiento, a.nombre
WITH READ ONLY;

CREATE OR REPLACE VIEW v_e3_auditoria_tarifa AS
SELECT id_auditoria, id_tarifa, usuario_oracle, fecha_cambio,
       precio_anterior, precio_nuevo, operacion, id_sentencia
FROM auditoria_tarifa
WITH READ ONLY;
