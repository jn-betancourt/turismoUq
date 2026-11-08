SELECT COUNT(*) AS pagos, SUM(monto) AS total
FROM pago
WHERE TRUNC(fecha_pago) >= :inicio AND TRUNC(fecha_pago) < :fin
