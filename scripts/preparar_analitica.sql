-- =============================================================================
-- TURISMOUQ - PREPARACION INICIAL DE OBJETOS ANALITICOS
-- Ejecutar como propietario, despues de DDL/migracion y carga verificada.
-- Requiere CREATE VIEW, CREATE MATERIALIZED VIEW y cuota suficiente.
-- No modifica reservas ni tarifas. El DDL confirma transacciones en Oracle.
-- Si ya existe la MV, revisar su definicion antes de recrearla explicitamente:
-- este script no elimina objetos existentes de forma automatica.
-- =============================================================================
SET DEFINE OFF
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';

CREATE OR REPLACE VIEW vw_calendario_mes AS
WITH extremos AS (
    SELECT fecha_inicio AS fecha FROM temporada
    UNION ALL
    SELECT fecha_fin FROM temporada
    UNION ALL
    SELECT fecha_checkin FROM reserva
    UNION ALL
    SELECT fecha_checkout - 1 FROM reserva
),
limites AS (
    SELECT TRUNC(MIN(fecha), 'MM') AS primer_mes,
           TRUNC(MAX(fecha), 'MM') AS ultimo_mes
    FROM extremos
),
meses AS (
    SELECT ADD_MONTHS(primer_mes, LEVEL - 1) AS mes
    FROM limites
    WHERE primer_mes IS NOT NULL
    CONNECT BY LEVEL <= MONTHS_BETWEEN(ultimo_mes, primer_mes) + 1
)
SELECT mes, ADD_MONTHS(mes, 1) AS mes_siguiente
FROM meses;

COMMENT ON TABLE vw_calendario_mes IS
    'Meses completos entre extremos de temporadas y noches de estadias; checkout excluido.';

CREATE OR REPLACE VIEW vw_ingreso_reserva AS
SELECT r.id_reserva,
       r.id_cliente,
       r.id_alojamiento,
       r.fecha_reserva,
       r.fecha_checkin,
       r.fecha_checkout,
       r.estado,
       NVL(h.hospedaje, 0) AS ingreso_hospedaje,
       NVL(s.servicios, 0) AS ingreso_servicios,
       NVL(h.hospedaje, 0) + NVL(s.servicios, 0) AS ingreso_total
FROM reserva r
LEFT JOIN (
    SELECT id_reserva, SUM(precio_estadia_habitacion) AS hospedaje
    FROM reserva_habitacion
    GROUP BY id_reserva
) h ON h.id_reserva = r.id_reserva
LEFT JOIN (
    SELECT id_reserva, SUM(subtotal) AS servicios
    FROM reserva_servicio
    GROUP BY id_reserva
) s ON s.id_reserva = r.id_reserva
WHERE r.estado <> 'CANCELADA';

COMMENT ON TABLE vw_ingreso_reserva IS
    'Ingreso contratado no cancelado: hospedaje guardado y servicios; incluye pendientes y futuros.';

-- Los importes provienen del contrato capturado, nunca de TARIFA actual.
-- Si no existe ningun tramo, se conserva el total legacy sin atribuir temporada.
-- Un detalle parcial/inconsistente debe impedir certificar el conjunto mediante
-- verificar_entrega1.sql; no se completa con precios ni repartos inferidos.
CREATE OR REPLACE VIEW vw_ingreso_hospedaje_temporada AS
SELECT r.id_reserva,
       rh.id_habitacion,
       h.id_alojamiento,
       a.id_municipio,
       a.id_tipo_alojamiento,
       CAST(tr.tipo_temporada_aplicado AS VARCHAR2(30)) AS tipo_temporada_aplicado,
       (tr.fecha_fin_tramo - tr.fecha_inicio_tramo) * tr.precio_noche_aplicado
           AS importe_hospedaje,
       CAST('SI' AS VARCHAR2(2)) AS desglose_verificado
FROM reserva_habitacion_tarifa_aplicada tr
JOIN reserva_habitacion rh
  ON rh.id_reserva = tr.id_reserva AND rh.id_habitacion = tr.id_habitacion
JOIN reserva r ON r.id_reserva = rh.id_reserva
JOIN habitacion h ON h.id_habitacion = rh.id_habitacion
JOIN alojamiento a ON a.id_alojamiento = h.id_alojamiento
WHERE r.estado <> 'CANCELADA'
UNION ALL
SELECT r.id_reserva,
       rh.id_habitacion,
       h.id_alojamiento,
       a.id_municipio,
       a.id_tipo_alojamiento,
       CAST('SIN DESGLOSE HISTORICO' AS VARCHAR2(30)),
       rh.precio_estadia_habitacion,
       CAST('NO' AS VARCHAR2(2))
FROM reserva_habitacion rh
JOIN reserva r ON r.id_reserva = rh.id_reserva
JOIN habitacion h ON h.id_habitacion = rh.id_habitacion
JOIN alojamiento a ON a.id_alojamiento = h.id_alojamiento
WHERE r.estado <> 'CANCELADA'
  AND NOT EXISTS (
      SELECT 1
      FROM reserva_habitacion_tarifa_aplicada tr
      WHERE tr.id_reserva = rh.id_reserva
        AND tr.id_habitacion = rh.id_habitacion
  );

COMMENT ON TABLE vw_ingreso_hospedaje_temporada IS
    'Tramos de precio aplicado y totales legacy sin desglose; no revalua con tarifas actuales.';

CREATE OR REPLACE VIEW vw_ocupacion_mensual_base AS
WITH inventario AS (
    SELECT id_alojamiento, COUNT(*) AS num_habitaciones
    FROM habitacion
    GROUP BY id_alojamiento
),
ocupacion AS (
    SELECT h.id_alojamiento,
           c.mes,
           SUM(
               LEAST(r.fecha_checkout, c.mes_siguiente)
               - GREATEST(r.fecha_checkin, c.mes)
           ) AS noches_ocupadas
    FROM reserva r
    JOIN reserva_habitacion rh ON rh.id_reserva = r.id_reserva
    JOIN habitacion h ON h.id_habitacion = rh.id_habitacion
    JOIN vw_calendario_mes c
      ON c.mes < r.fecha_checkout
     AND c.mes_siguiente > r.fecha_checkin
    WHERE r.estado <> 'CANCELADA'
    GROUP BY h.id_alojamiento, c.mes
),
base AS (
    SELECT a.id_municipio,
           a.id_alojamiento,
           c.mes,
           NVL(o.noches_ocupadas, 0) AS noches_ocupadas,
           NVL(i.num_habitaciones, 0) * (c.mes_siguiente - c.mes)
               AS noches_disponibles
    FROM alojamiento a
    CROSS JOIN vw_calendario_mes c
    LEFT JOIN inventario i ON i.id_alojamiento = a.id_alojamiento
    LEFT JOIN ocupacion o ON o.id_alojamiento = a.id_alojamiento AND o.mes = c.mes
)
SELECT id_municipio,
       id_alojamiento,
       mes,
       noches_ocupadas,
       noches_disponibles,
       100 * noches_ocupadas / NULLIF(noches_disponibles, 0) AS pct_ocupacion
FROM base;

COMMENT ON TABLE vw_ocupacion_mensual_base IS
    'Ocupacion reservada no cancelada por mes sobre inventario bruto actual; sin limite de noches.';

-- POLITICA: COMPLETE ON DEMAND despues de carga/cambios y antes de evidencia.
-- Se acepta desfase hasta el refresco manual documentado; esta MV no valida
-- disponibilidad operativa. No se instala ni se afirma un job diario.
-- COMPLETE evita depender de condiciones de FAST para el calendario generado,
-- uniones externas y agregacion por interseccion; no se prometen ventajas sin
-- medir planes/tiempos. ON DEMAND evita trabajo adicional en cada COMMIT.
CREATE MATERIALIZED VIEW mv_ocupacion_mensual
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT id_municipio,
       id_alojamiento,
       mes,
       noches_ocupadas,
       noches_disponibles,
       pct_ocupacion
FROM vw_ocupacion_mensual_base;

COMMENT ON MATERIALIZED VIEW mv_ocupacion_mensual IS
    'Ocupacion reservada sobre inventario bruto; COMPLETE ON DEMAND antes de producir evidencia.';

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'VW_CALENDARIO_MES', 'VW_INGRESO_RESERVA',
    'VW_INGRESO_HOSPEDAJE_TEMPORADA', 'VW_OCUPACION_MENSUAL_BASE',
    'MV_OCUPACION_MENSUAL'
)
ORDER BY object_name, object_type;
