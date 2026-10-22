-- =============================================================================
-- TURISMOUQ - ACEPTACION DE ESTRUCTURA Y DATOS DE LA ENTREGA 1
-- Solo lectura. No reconstruye tarifas historicas, no carga ni corrige datos.
-- Ejecutar con SQL*Plus / SQLcl / Run Script, conectado al esquema del proyecto.
-- Un error cancela la corrida con codigo distinto de cero. Conservar el spool.
-- Las ocho consultas y su vista materializada tienen verificaciones separadas.
-- =============================================================================
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
SET SERVEROUTPUT ON
SET SQLBLANKLINES ON
SET DEFINE OFF

PROMPT === VERIFICACION DE ESTRUCTURA Y DATOS TURISMOUQ ===

-- El control de catalogo se compila antes de referenciar la tabla de tramos.
-- Una base de 21 tablas recibe un diagnostico explicito de evidencia parcial.
DECLARE
    v_tablas_base PLS_INTEGER;
    v_tabla_tramos PLS_INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_tablas_base FROM user_tables
    WHERE table_name IN (
        'USUARIO_SISTEMA', 'PROPIETARIO', 'CLIENTE', 'MUNICIPIO',
        'TIPO_ALOJAMIENTO', 'ALOJAMIENTO', 'TIPO_HABITACION', 'HABITACION',
        'COMODIDAD', 'ALOJAMIENTO_COMODIDAD', 'TEMPORADA', 'TARIFA',
        'AUDITORIA_TARIFA', 'RESERVA', 'RESERVA_HABITACION', 'PAGO',
        'SERVICIO', 'RESERVA_SERVICIO', 'RESENA', 'LIQUIDACION_MENSUAL',
        'HISTORICO_RESERVA'
    );
    IF v_tablas_base <> 21 THEN
        RAISE_APPLICATION_ERROR(-20100,
            'NO CERTIFICADO: faltan tablas del modelo base; observadas=' || v_tablas_base || '/21.');
    END IF;
    SELECT COUNT(*) INTO v_tabla_tramos FROM user_tables
    WHERE table_name = 'RESERVA_HABITACION_TARIFA_APLICADA';
    IF v_tabla_tramos <> 1 THEN
        DBMS_OUTPUT.PUT_LINE('ESTADO=PARCIAL: esquema legacy sin precios originales por tramos.');
        RAISE_APPLICATION_ERROR(-20101,
            'PARCIAL: falta RESERVA_HABITACION_TARIFA_APLICADA. No se certifica ni se reconstruye.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('OK: las 22 tablas del modelo estan presentes.');
END;
/

DECLARE
    v_cantidad NUMBER;
    v_inicio_calendario DATE;
    v_fin_calendario DATE;
    v_primer_checkin DATE;
    v_ultimo_checkout DATE;

    PROCEDURE assert_zero(p_criterio VARCHAR2, p_cantidad NUMBER,
                          p_codigo PLS_INTEGER) IS
    BEGIN
        IF p_cantidad IS NULL OR p_cantidad <> 0 THEN
            RAISE_APPLICATION_ERROR(p_codigo,
                'NO CERTIFICADO: ' || p_criterio || '; anomalias=' || NVL(TO_CHAR(p_cantidad), 'NULL'));
        END IF;
        DBMS_OUTPUT.PUT_LINE('OK: ' || p_criterio || ' = 0.');
    END;

    PROCEDURE assert_minimum(p_tabla VARCHAR2, p_minimo NUMBER) IS
        v_filas NUMBER;
    BEGIN
        -- Los nombres son constantes de este script, nunca entrada del usuario.
        EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM "' || p_tabla || '"' INTO v_filas;
        IF v_filas < p_minimo THEN
            RAISE_APPLICATION_ERROR(-20102, 'NO CERTIFICADO: ' || p_tabla
                || '; filas=' || v_filas || '; minimo=' || p_minimo);
        END IF;
        DBMS_OUTPUT.PUT_LINE('OK: ' || p_tabla || '=' || v_filas || '; minimo=' || p_minimo);
    END;

    PROCEDURE assert_unique_key(p_tabla VARCHAR2, p_columnas VARCHAR2) IS
        v_llaves PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_llaves FROM user_constraints llave
        WHERE llave.table_name = p_tabla AND llave.constraint_type IN ('P', 'U')
          AND (SELECT LISTAGG(c.column_name, ',') WITHIN GROUP (ORDER BY c.position)
               FROM user_cons_columns c
               WHERE c.constraint_name = llave.constraint_name AND c.owner = llave.owner) = p_columnas;
        IF v_llaves <> 1 THEN
            RAISE_APPLICATION_ERROR(-20126, 'NO CERTIFICADO: llave unica requerida '
                || p_tabla || '(' || p_columnas || ') ausente o ambigua.');
        END IF;
    END;

    PROCEDURE assert_foreign_key(p_tabla VARCHAR2, p_columnas VARCHAR2,
                                 p_tabla_padre VARCHAR2, p_columnas_padre VARCHAR2) IS
        v_llaves PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_llaves
        FROM user_constraints hija
        JOIN user_constraints padre ON padre.constraint_name = hija.r_constraint_name
                                   AND padre.owner = hija.r_owner
        WHERE hija.constraint_type = 'R' AND hija.table_name = p_tabla
          AND padre.table_name = p_tabla_padre
          AND (SELECT LISTAGG(c.column_name, ',') WITHIN GROUP (ORDER BY c.position)
               FROM user_cons_columns c
               WHERE c.constraint_name = hija.constraint_name AND c.owner = hija.owner) = p_columnas
          AND (SELECT LISTAGG(c.column_name, ',') WITHIN GROUP (ORDER BY c.position)
               FROM user_cons_columns c
               WHERE c.constraint_name = padre.constraint_name AND c.owner = padre.owner) = p_columnas_padre;
        IF v_llaves <> 1 THEN
            RAISE_APPLICATION_ERROR(-20103, 'NO CERTIFICADO: FK requerida '
                || p_tabla || '(' || p_columnas || ') -> ' || p_tabla_padre || ' ausente o ambigua.');
        END IF;
    END;
BEGIN
    assert_minimum('MUNICIPIO', 12);
    assert_minimum('ALOJAMIENTO', 60);
    assert_minimum('HABITACION', 400);
    assert_minimum('CLIENTE', 3000);
    assert_minimum('RESERVA', 25000);
    assert_minimum('RESERVA_SERVICIO', 40000);

    SELECT COUNT(*) INTO v_cantidad FROM user_constraints
    WHERE table_name IN (
        'USUARIO_SISTEMA', 'PROPIETARIO', 'CLIENTE', 'MUNICIPIO',
        'TIPO_ALOJAMIENTO', 'ALOJAMIENTO', 'TIPO_HABITACION', 'HABITACION',
        'COMODIDAD', 'ALOJAMIENTO_COMODIDAD', 'TEMPORADA', 'TARIFA',
        'AUDITORIA_TARIFA', 'RESERVA', 'RESERVA_HABITACION', 'PAGO',
        'SERVICIO', 'RESERVA_SERVICIO', 'RESENA', 'LIQUIDACION_MENSUAL',
        'HISTORICO_RESERVA', 'RESERVA_HABITACION_TARIFA_APLICADA'
    ) AND (status <> 'ENABLED' OR validated <> 'VALIDATED');
    assert_zero('Restricciones deshabilitadas o sin validar', v_cantidad, -20104);

    SELECT 22 - COUNT(*) INTO v_cantidad FROM user_constraints
    WHERE constraint_type = 'P' AND table_name IN (
        'USUARIO_SISTEMA', 'PROPIETARIO', 'CLIENTE', 'MUNICIPIO',
        'TIPO_ALOJAMIENTO', 'ALOJAMIENTO', 'TIPO_HABITACION', 'HABITACION',
        'COMODIDAD', 'ALOJAMIENTO_COMODIDAD', 'TEMPORADA', 'TARIFA',
        'AUDITORIA_TARIFA', 'RESERVA', 'RESERVA_HABITACION', 'PAGO',
        'SERVICIO', 'RESERVA_SERVICIO', 'RESENA', 'LIQUIDACION_MENSUAL',
        'HISTORICO_RESERVA', 'RESERVA_HABITACION_TARIFA_APLICADA'
    );
    assert_zero('Tablas sin llave primaria', v_cantidad, -20105);

    assert_unique_key('USUARIO_SISTEMA', 'USERNAME');
    assert_unique_key('USUARIO_SISTEMA', 'EMAIL');
    assert_unique_key('PROPIETARIO', 'DOCUMENTO_IDENTIDAD');
    assert_unique_key('CLIENTE', 'NUMERO_DOCUMENTO');
    assert_unique_key('MUNICIPIO', 'NOMBRE');
    assert_unique_key('TIPO_ALOJAMIENTO', 'NOMBRE');
    assert_unique_key('TIPO_HABITACION', 'NOMBRE');
    assert_unique_key('COMODIDAD', 'NOMBRE');
    assert_unique_key('ALOJAMIENTO', 'ID_MUNICIPIO,NOMBRE');
    assert_unique_key('HABITACION', 'ID_ALOJAMIENTO,NUMERO_HABITACION');
    assert_unique_key('SERVICIO', 'ID_ALOJAMIENTO,NOMBRE');
    assert_unique_key('TEMPORADA', 'NOMBRE,FECHA_INICIO,FECHA_FIN');
    assert_unique_key('TARIFA', 'ID_HABITACION,ID_TEMPORADA');
    assert_unique_key('RESENA', 'ID_RESERVA');
    assert_unique_key('LIQUIDACION_MENSUAL', 'ID_ALOJAMIENTO,PERIODO_ANIO,PERIODO_MES');
    assert_unique_key('RESERVA_HABITACION_TARIFA_APLICADA',
                      'ID_RESERVA,ID_HABITACION,FECHA_INICIO_TRAMO');
    DBMS_OUTPUT.PUT_LINE('OK: llaves unicas requeridas y llave de tramos historicos.');

    assert_foreign_key('PROPIETARIO', 'ID_USUARIO', 'USUARIO_SISTEMA', 'ID_USUARIO');
    assert_foreign_key('CLIENTE', 'ID_USUARIO', 'USUARIO_SISTEMA', 'ID_USUARIO');
    assert_foreign_key('ALOJAMIENTO', 'ID_PROPIETARIO', 'PROPIETARIO', 'ID_USUARIO');
    assert_foreign_key('ALOJAMIENTO', 'ID_MUNICIPIO', 'MUNICIPIO', 'ID_MUNICIPIO');
    assert_foreign_key('ALOJAMIENTO', 'ID_TIPO_ALOJAMIENTO', 'TIPO_ALOJAMIENTO', 'ID_TIPO_ALOJAMIENTO');
    assert_foreign_key('HABITACION', 'ID_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    assert_foreign_key('HABITACION', 'ID_TIPO_HABITACION', 'TIPO_HABITACION', 'ID_TIPO_HABITACION');
    assert_foreign_key('ALOJAMIENTO_COMODIDAD', 'ID_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    assert_foreign_key('ALOJAMIENTO_COMODIDAD', 'ID_COMODIDAD', 'COMODIDAD', 'ID_COMODIDAD');
    assert_foreign_key('SERVICIO', 'ID_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    assert_foreign_key('TARIFA', 'ID_HABITACION', 'HABITACION', 'ID_HABITACION');
    assert_foreign_key('TARIFA', 'ID_TEMPORADA', 'TEMPORADA', 'ID_TEMPORADA');
    assert_foreign_key('AUDITORIA_TARIFA', 'ID_TARIFA', 'TARIFA', 'ID_TARIFA');
    assert_foreign_key('RESERVA', 'ID_CLIENTE', 'CLIENTE', 'ID_USUARIO');
    assert_foreign_key('RESERVA', 'ID_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    assert_foreign_key('RESERVA_HABITACION', 'ID_RESERVA', 'RESERVA', 'ID_RESERVA');
    assert_foreign_key('RESERVA_HABITACION', 'ID_HABITACION', 'HABITACION', 'ID_HABITACION');
    assert_foreign_key('RESERVA_HABITACION_TARIFA_APLICADA', 'ID_RESERVA,ID_HABITACION',
                       'RESERVA_HABITACION', 'ID_RESERVA,ID_HABITACION');
    assert_foreign_key('RESERVA_HABITACION_TARIFA_APLICADA', 'ID_TEMPORADA', 'TEMPORADA', 'ID_TEMPORADA');
    assert_foreign_key('PAGO', 'ID_RESERVA', 'RESERVA', 'ID_RESERVA');
    assert_foreign_key('PAGO', 'ID_CLIENTE', 'CLIENTE', 'ID_USUARIO');
    assert_foreign_key('RESERVA_SERVICIO', 'ID_RESERVA', 'RESERVA', 'ID_RESERVA');
    assert_foreign_key('RESERVA_SERVICIO', 'ID_SERVICIO', 'SERVICIO', 'ID_SERVICIO');
    assert_foreign_key('RESENA', 'ID_RESERVA', 'RESERVA', 'ID_RESERVA');
    assert_foreign_key('RESENA', 'ID_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    assert_foreign_key('LIQUIDACION_MENSUAL', 'ID_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    assert_foreign_key('HISTORICO_RESERVA', 'ID_RESERVA', 'RESERVA', 'ID_RESERVA');
    DBMS_OUTPUT.PUT_LINE('OK: llaves foraneas requeridas, incluida la FK compuesta de tramos.');

    SELECT COUNT(*) INTO v_cantidad FROM reserva
    WHERE id_alojamiento IS NULL OR fecha_checkin <> TRUNC(fecha_checkin)
       OR fecha_checkout <> TRUNC(fecha_checkout) OR fecha_checkout <= fecha_checkin;
    assert_zero('Reservas sin alojamiento o con fechas invalidas/con hora', v_cantidad, -20106);

    SELECT COUNT(*) INTO v_cantidad FROM reserva r
    WHERE NOT EXISTS (SELECT 1 FROM reserva_habitacion rh WHERE rh.id_reserva = r.id_reserva);
    assert_zero('Reservas sin habitaciones asignadas', v_cantidad, -20107);

    SELECT COUNT(*) INTO v_cantidad
    FROM reserva_habitacion rh JOIN reserva r ON r.id_reserva = rh.id_reserva
    JOIN habitacion h ON h.id_habitacion = rh.id_habitacion
    JOIN tipo_habitacion th ON th.id_tipo_habitacion = h.id_tipo_habitacion
    WHERE h.id_alojamiento <> r.id_alojamiento
       OR rh.personas_hospedadas <= 0 OR rh.personas_hospedadas > th.capacidad_estandar;
    assert_zero('Habitaciones de otro alojamiento o con capacidad excedida', v_cantidad, -20108);

    SELECT COUNT(*) INTO v_cantidad
    FROM reserva_servicio rs JOIN reserva r ON r.id_reserva = rs.id_reserva
    JOIN servicio s ON s.id_servicio = rs.id_servicio
    WHERE s.id_alojamiento <> r.id_alojamiento
       OR rs.subtotal <> ROUND(rs.cantidad * rs.precio_unitario_aplicado, 2);
    assert_zero('Servicios de otro alojamiento o con subtotal inconsistente', v_cantidad, -20109);

    SELECT COUNT(*) INTO v_cantidad FROM pago p JOIN reserva r ON r.id_reserva = p.id_reserva
    WHERE p.id_cliente <> r.id_cliente;
    assert_zero('Pagos asociados a otro cliente', v_cantidad, -20110);

    SELECT COUNT(*) INTO v_cantidad FROM resena s JOIN reserva r ON r.id_reserva = s.id_reserva
    WHERE s.id_alojamiento <> r.id_alojamiento OR r.estado <> 'FINALIZADA';
    assert_zero('Resenas de otro alojamiento o de estadias no finalizadas', v_cantidad, -20111);

    SELECT COUNT(*) INTO v_cantidad FROM temporada
    WHERE fecha_inicio <> TRUNC(fecha_inicio) OR fecha_fin <> TRUNC(fecha_fin)
       OR fecha_fin < fecha_inicio;
    assert_zero('Temporadas con fechas invalidas/con hora', v_cantidad, -20112);

    SELECT COUNT(*) INTO v_cantidad FROM temporada a JOIN temporada b
      ON b.id_temporada > a.id_temporada
     AND a.fecha_inicio <= b.fecha_fin AND b.fecha_inicio <= a.fecha_fin;
    assert_zero('Temporadas solapadas', v_cantidad, -20113);

    SELECT COUNT(*) INTO v_cantidad FROM (
        SELECT fecha_inicio, LAG(fecha_fin) OVER (ORDER BY fecha_inicio, id_temporada) AS fin_anterior
        FROM temporada
    ) WHERE fin_anterior IS NOT NULL AND fecha_inicio <> fin_anterior + 1;
    assert_zero('Discontinuidades en el calendario de temporadas', v_cantidad, -20114);

    SELECT MIN(fecha_inicio), MAX(fecha_fin) INTO v_inicio_calendario, v_fin_calendario FROM temporada;
    SELECT MIN(fecha_checkin), MAX(fecha_checkout) INTO v_primer_checkin, v_ultimo_checkout FROM reserva;
    IF v_inicio_calendario IS NULL OR v_fin_calendario IS NULL
       OR v_inicio_calendario > v_primer_checkin OR v_fin_calendario + 1 < v_ultimo_checkout THEN
        RAISE_APPLICATION_ERROR(-20115, 'NO CERTIFICADO: temporadas no cubren todas las noches reservadas.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('OK: cobertura unica y continua de temporadas durante todas las estadias.');

    SELECT COUNT(*) INTO v_cantidad FROM habitacion h CROSS JOIN temporada t
    WHERE NOT EXISTS (SELECT 1 FROM tarifa ta WHERE ta.id_habitacion = h.id_habitacion
                      AND ta.id_temporada = t.id_temporada AND ta.precio_noche > 0);
    assert_zero('Combinaciones habitacion/temporada sin tarifa positiva', v_cantidad, -20116);

    SELECT COUNT(*) INTO v_cantidad FROM (
        SELECT id_habitacion, id_temporada FROM tarifa
        GROUP BY id_habitacion, id_temporada HAVING COUNT(*) <> 1
    );
    assert_zero('Combinaciones habitacion/temporada duplicadas', v_cantidad, -20117);

    SELECT COUNT(*) INTO v_cantidad
    FROM reserva_habitacion a JOIN reserva ra ON ra.id_reserva = a.id_reserva
    JOIN reserva_habitacion b ON b.id_habitacion = a.id_habitacion AND b.id_reserva > a.id_reserva
    JOIN reserva rb ON rb.id_reserva = b.id_reserva
    WHERE ra.estado <> 'CANCELADA' AND rb.estado <> 'CANCELADA'
      AND ra.fecha_checkin < rb.fecha_checkout AND rb.fecha_checkin < ra.fecha_checkout;
    assert_zero('Reservas no canceladas solapadas por habitacion', v_cantidad, -20118);

    SELECT COUNT(*) INTO v_cantidad FROM reserva_habitacion rh
    WHERE NOT EXISTS (SELECT 1 FROM reserva_habitacion_tarifa_aplicada t
                      WHERE t.id_reserva = rh.id_reserva AND t.id_habitacion = rh.id_habitacion);
    IF v_cantidad <> 0 THEN
        DBMS_OUTPUT.PUT_LINE('ESTADO=PARCIAL: detalles sin precios originales=' || v_cantidad);
        RAISE_APPLICATION_ERROR(-20119,
            'PARCIAL: faltan tramos de tarifas aplicadas. No se certifica ni se infiere desde TARIFA actual.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('OK: todas las habitaciones reservadas tienen evidencia de tarifa aplicada.');

    SELECT COUNT(*) INTO v_cantidad FROM reserva_habitacion_tarifa_aplicada
    WHERE fecha_inicio_tramo <> TRUNC(fecha_inicio_tramo)
       OR fecha_fin_tramo <> TRUNC(fecha_fin_tramo) OR fecha_fin_tramo <= fecha_inicio_tramo
       OR precio_noche_aplicado <= 0 OR tipo_temporada_aplicado NOT IN ('ALTA', 'MEDIA', 'BAJA')
       OR origen_dato NOT IN ('CAPTURADO', 'RECONSTRUIDO_VALIDADO')
       OR (origen_dato = 'RECONSTRUIDO_VALIDADO' AND TRIM(referencia_evidencia) IS NULL);
    assert_zero('Tramos con fechas, precio, tipo u origen/evidencia invalidos', v_cantidad, -20120);

    SELECT COUNT(*) INTO v_cantidad FROM (
        SELECT t.id_reserva, t.id_habitacion, t.fecha_inicio_tramo, t.fecha_fin_tramo,
               LAG(t.fecha_fin_tramo) OVER (
                   PARTITION BY t.id_reserva, t.id_habitacion ORDER BY t.fecha_inicio_tramo
               ) AS fin_anterior
        FROM reserva_habitacion_tarifa_aplicada t
    ) tramos JOIN reserva r ON r.id_reserva = tramos.id_reserva
    WHERE tramos.fecha_inicio_tramo < r.fecha_checkin OR tramos.fecha_fin_tramo > r.fecha_checkout
       OR (tramos.fin_anterior IS NOT NULL AND tramos.fin_anterior <> tramos.fecha_inicio_tramo);
    assert_zero('Tramos fuera de estadia, con huecos o solapados', v_cantidad, -20121);

    SELECT COUNT(*) INTO v_cantidad
    FROM reserva_habitacion rh JOIN reserva r ON r.id_reserva = rh.id_reserva
    JOIN (
        SELECT id_reserva, id_habitacion, MIN(fecha_inicio_tramo) AS inicio,
               MAX(fecha_fin_tramo) AS fin,
               SUM(fecha_fin_tramo - fecha_inicio_tramo) AS noches,
               SUM((fecha_fin_tramo - fecha_inicio_tramo) * precio_noche_aplicado) AS importe
        FROM reserva_habitacion_tarifa_aplicada GROUP BY id_reserva, id_habitacion
    ) tramos ON tramos.id_reserva = rh.id_reserva AND tramos.id_habitacion = rh.id_habitacion
    WHERE tramos.inicio <> r.fecha_checkin OR tramos.fin <> r.fecha_checkout
       OR tramos.noches <> r.fecha_checkout - r.fecha_checkin
       OR tramos.importe <> rh.precio_estadia_habitacion;
    assert_zero('Cobertura exacta e importe historico por habitacion inconsistentes', v_cantidad, -20122);

    -- Se compara con el precio CAPTURADO, nunca con la tarifa actual mutable.
    SELECT COUNT(*) INTO v_cantidad FROM reserva r
    WHERE r.valor_total <>
          (SELECT NVL(SUM(rh.precio_estadia_habitacion), 0) FROM reserva_habitacion rh
           WHERE rh.id_reserva = r.id_reserva)
        + (SELECT NVL(SUM(rs.subtotal), 0) FROM reserva_servicio rs WHERE rs.id_reserva = r.id_reserva);
    assert_zero('Totales de reserva distintos de hospedaje mas servicios', v_cantidad, -20123);

    SELECT 1 - COUNT(*) INTO v_cantidad FROM user_tables
    WHERE table_name = 'HISTORICO_RESERVA' AND tablespace_name = 'TS_HISTORICO_RESERVAS';
    assert_zero('Tabla historica fuera de su tablespace propio', v_cantidad, -20124);
    SELECT COUNT(*) INTO v_cantidad FROM user_indexes
    WHERE table_name = 'HISTORICO_RESERVA'
      AND NVL(tablespace_name, '?') <> 'TS_HISTORICO_RESERVAS';
    assert_zero('Indices historicos fuera del tablespace propio', v_cantidad, -20125);

    SELECT COUNT(*) INTO v_cantidad FROM reserva_habitacion_tarifa_aplicada
    WHERE origen_dato = 'RECONSTRUIDO_VALIDADO';
    DBMS_OUTPUT.PUT_LINE('INFORMACION: tramos reconstruidos con evidencia declarada=' || v_cantidad);
    DBMS_OUTPUT.PUT_LINE('VERIFICACION ESTRUCTURA Y DATOS E1: APROBADA.');
    DBMS_OUTPUT.PUT_LINE('Esta verificacion no acredita por si sola la ejecucion de las ocho consultas.');
END;
/
