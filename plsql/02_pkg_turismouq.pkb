-- TURISMOUQ - Entrega 2. Implementacion del paquete, sin COMMIT interno.
SET DEFINE OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE PACKAGE BODY pkg_turismouq AS
    c_maximo_reserva CONSTANT NUMBER := 9999999999.99;
    c_maximo_liquidacion CONSTANT NUMBER := 999999999999.99;

    TYPE tipo_tramo IS RECORD (
        fecha_inicio DATE,
        fecha_fin DATE,
        id_temporada NUMBER,
        tipo_temporada VARCHAR2(5),
        precio_noche NUMBER
    );
    TYPE lista_tramos IS TABLE OF tipo_tramo INDEX BY PLS_INTEGER;
    TYPE tipo_habitacion_capturada IS RECORD (
        id_habitacion NUMBER,
        personas NUMBER,
        importe NUMBER,
        tramos lista_tramos
    );
    TYPE lista_habitaciones_capturadas IS TABLE OF tipo_habitacion_capturada
        INDEX BY PLS_INTEGER;
    TYPE tipo_servicio_capturado IS RECORD (
        id_servicio NUMBER,
        cantidad NUMBER,
        precio NUMBER,
        subtotal NUMBER
    );
    TYPE lista_servicios_capturados IS TABLE OF tipo_servicio_capturado
        INDEX BY PLS_INTEGER;

    PROCEDURE validar_fechas(p_fecha_in DATE, p_fecha_out DATE) IS
    BEGIN
        IF p_fecha_in IS NULL OR p_fecha_out IS NULL
           OR p_fecha_in <> TRUNC(p_fecha_in)
           OR p_fecha_out <> TRUNC(p_fecha_out)
           OR p_fecha_in >= DATE '9999-12-31'
           OR p_fecha_out >= DATE '9999-12-31' THEN
            RAISE_APPLICATION_ERROR(c_error_fechas,
                'Fechas obligatorias sin hora; el extremo 9999-12-31 no esta soportado.');
        END IF;
        IF p_fecha_out <= p_fecha_in THEN
            RAISE_APPLICATION_ERROR(c_error_checkout,
                'El checkout debe ser posterior al check-in.');
        END IF;
    END validar_fechas;

    PROCEDURE validar_importe(p_importe NUMBER, p_maximo NUMBER) IS
    BEGIN
        IF p_importe IS NULL OR p_importe < 0 OR p_importe > p_maximo
           OR p_importe <> ROUND(p_importe, 2) THEN
            RAISE_APPLICATION_ERROR(c_error_importe,
                'El importe excede la capacidad monetaria o no tiene precision de centavos.');
        END IF;
    END validar_importe;

    -- SQL ordena y deduplica sin recorridos cuadraticos. El tipo esta declarado
    -- en la especificacion publica y Oracle 21c admite TABLE en esta lectura.
    -- NULL, vacias y dispersas tienen el mismo resultado normalizado.
    PROCEDURE ordenar_identificadores(
        p_entrada lista_identificadores,
        p_salida OUT lista_identificadores
    ) IS
        v_cantidad PLS_INTEGER;
    BEGIN
        p_salida := lista_identificadores();
        BEGIN
            v_cantidad := p_entrada.COUNT;
        EXCEPTION
            WHEN COLLECTION_IS_NULL THEN RETURN;
        END;
        IF v_cantidad = 0 THEN RETURN; END IF;
        SELECT DISTINCT column_value
        BULK COLLECT INTO p_salida
        FROM TABLE(p_entrada)
        WHERE column_value IS NOT NULL
        ORDER BY column_value;
    END ordenar_identificadores;

    PROCEDURE bloquear_identificador(p_entidad VARCHAR2, p_identificador NUMBER) IS
        v_sentencia VARCHAR2(400);
        v_identificador NUMBER;
    BEGIN
        -- Los nombres son una lista cerrada interna; solamente el ID es un bind.
        CASE p_entidad
            WHEN 'RESERVA' THEN
                v_sentencia := 'SELECT id_reserva FROM reserva WHERE id_reserva = :id';
            WHEN 'HABITACION' THEN
                v_sentencia := 'SELECT id_habitacion FROM habitacion WHERE id_habitacion = :id';
            WHEN 'ALOJAMIENTO' THEN
                v_sentencia := 'SELECT id_alojamiento FROM alojamiento WHERE id_alojamiento = :id';
            ELSE
                RAISE PROGRAM_ERROR;
        END CASE;
        v_sentencia := v_sentencia || ' FOR UPDATE WAIT '
            || TO_CHAR(c_espera_bloqueo_segundos, 'FM9990');
        EXECUTE IMMEDIATE v_sentencia INTO v_identificador USING p_identificador;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            IF p_entidad = 'HABITACION' THEN
                RAISE_APPLICATION_ERROR(c_error_habitacion, 'La habitacion no existe.');
            ELSE
                RAISE_APPLICATION_ERROR(c_error_referencia,
                    'La reserva o el alojamiento requerido no existe.');
            END IF;
        WHEN OTHERS THEN
            IF SQLCODE IN (-30006, -54) THEN
                RAISE_APPLICATION_ERROR(c_error_bloqueo,
                    'Recurso ocupado: se agoto la espera de bloqueo; reintente la transaccion.');
            END IF;
            RAISE;
    END bloquear_identificador;

    PROCEDURE capturar_tramos(
        p_id_habitacion NUMBER,
        p_fecha_in DATE,
        p_fecha_out DATE,
        p_tramos OUT lista_tramos,
        p_importe OUT NUMBER
    ) IS
        v_cantidad PLS_INTEGER;
        v_siguiente DATE;
        v_inicio DATE;
        v_fin DATE;
        v_indice PLS_INTEGER := 0;
    BEGIN
        validar_fechas(p_fecha_in, p_fecha_out);
        SELECT COUNT(*) INTO v_cantidad
        FROM habitacion WHERE id_habitacion = p_id_habitacion;
        IF v_cantidad <> 1 THEN
            RAISE_APPLICATION_ERROR(c_error_habitacion, 'La habitacion no existe.');
        END IF;
        p_tramos.DELETE;
        p_importe := 0;
        v_siguiente := p_fecha_in;
        -- Una sola apertura captura todos los precios de esta habitacion.
        -- El filtro inclusivo evita sumar un dia antes de validar el maximo DATE.
        FOR temporada_actual IN (
            SELECT t.id_temporada, t.fecha_inicio, t.fecha_fin,
                   t.tipo_temporada, ta.precio_noche
            FROM temporada t
            LEFT JOIN tarifa ta
              ON ta.id_temporada = t.id_temporada
             AND ta.id_habitacion = p_id_habitacion
            WHERE t.fecha_inicio < p_fecha_out AND t.fecha_fin >= p_fecha_in
            ORDER BY t.fecha_inicio, t.id_temporada
        ) LOOP
            IF temporada_actual.fecha_inicio <> TRUNC(temporada_actual.fecha_inicio)
               OR temporada_actual.fecha_fin <> TRUNC(temporada_actual.fecha_fin)
               OR temporada_actual.fecha_fin < temporada_actual.fecha_inicio
               OR temporada_actual.fecha_fin >= DATE '9999-12-31' THEN
                RAISE_APPLICATION_ERROR(c_error_fechas,
                    'La temporada tiene horas, fechas invalidas o un extremo no soportado.');
            END IF;
            v_inicio := GREATEST(p_fecha_in, temporada_actual.fecha_inicio);
            v_fin := LEAST(p_fecha_out, temporada_actual.fecha_fin + 1);
            IF v_inicio > v_siguiente THEN
                RAISE_APPLICATION_ERROR(c_error_cobertura,
                    'Existe una noche sin temporada en el intervalo solicitado.');
            ELSIF v_inicio < v_siguiente THEN
                RAISE_APPLICATION_ERROR(c_error_temporadas,
                    'Existen temporadas superpuestas en el intervalo solicitado.');
            END IF;
            IF temporada_actual.precio_noche IS NULL
               OR temporada_actual.precio_noche <= 0 THEN
                RAISE_APPLICATION_ERROR(c_error_tarifa,
                    'Falta una tarifa positiva de la habitacion para una temporada.');
            END IF;
            v_indice := v_indice + 1;
            p_tramos(v_indice).fecha_inicio := v_inicio;
            p_tramos(v_indice).fecha_fin := v_fin;
            p_tramos(v_indice).id_temporada := temporada_actual.id_temporada;
            p_tramos(v_indice).tipo_temporada := temporada_actual.tipo_temporada;
            p_tramos(v_indice).precio_noche := temporada_actual.precio_noche;
            p_importe := p_importe
                + (v_fin - v_inicio) * temporada_actual.precio_noche;
            validar_importe(p_importe, c_maximo_reserva);
            v_siguiente := v_fin;
        END LOOP;
        IF v_siguiente <> p_fecha_out THEN
            RAISE_APPLICATION_ERROR(c_error_cobertura,
                'Las temporadas no cubren todas las noches de la estadia.');
        END IF;
        p_importe := ROUND(p_importe, 2);
    END capturar_tramos;

    FUNCTION fn_valor_estadia(
        p_id_habitacion IN NUMBER,
        p_fecha_in IN DATE,
        p_fecha_out IN DATE
    ) RETURN NUMBER IS
        v_tramos lista_tramos;
        v_importe NUMBER;
    BEGIN
        capturar_tramos(p_id_habitacion, p_fecha_in, p_fecha_out, v_tramos, v_importe);
        RETURN v_importe;
    END fn_valor_estadia;

    PROCEDURE validar_reservas(
        p_ids_reserva IN lista_identificadores,
        p_ids_habitacion_adicionales IN lista_identificadores
    ) IS
        v_reservas lista_identificadores;
        v_habitaciones lista_identificadores;
        v_habitaciones_ordenadas lista_identificadores;
        v_entrada DATE;
        v_salida DATE;
        v_alojamiento NUMBER;
        v_cantidad PLS_INTEGER;
    BEGIN
        ordenar_identificadores(p_ids_reserva, v_reservas);
        ordenar_identificadores(p_ids_habitacion_adicionales, v_habitaciones);
        FOR i IN 1 .. v_reservas.COUNT LOOP
            bloquear_identificador('RESERVA', v_reservas(i));
        END LOOP;
        FOR i IN 1 .. v_reservas.COUNT LOOP
            FOR detalle IN (
                SELECT id_habitacion FROM reserva_habitacion
                WHERE id_reserva = v_reservas(i)
            ) LOOP
                v_habitaciones.EXTEND;
                v_habitaciones(v_habitaciones.COUNT) := detalle.id_habitacion;
            END LOOP;
        END LOOP;
        ordenar_identificadores(v_habitaciones, v_habitaciones_ordenadas);
        FOR i IN 1 .. v_habitaciones_ordenadas.COUNT LOOP
            bloquear_identificador('HABITACION', v_habitaciones_ordenadas(i));
        END LOOP;

        FOR i IN 1 .. v_reservas.COUNT LOOP
            SELECT fecha_checkin, fecha_checkout, id_alojamiento
            INTO v_entrada, v_salida, v_alojamiento
            FROM reserva WHERE id_reserva = v_reservas(i);
            validar_fechas(v_entrada, v_salida);
            IF v_alojamiento IS NULL THEN
                RAISE_APPLICATION_ERROR(c_error_referencia,
                    'La reserva debe tener un alojamiento coherente con sus habitaciones.');
            END IF;
            SELECT COUNT(*) INTO v_cantidad
            FROM reserva_habitacion WHERE id_reserva = v_reservas(i);
            IF v_cantidad = 0 THEN
                RAISE_APPLICATION_ERROR(c_error_integridad,
                    'La reserva afectada no tiene habitaciones asignadas.');
            END IF;
            FOR detalle IN (
                SELECT rh.personas_hospedadas, h.id_alojamiento, th.capacidad_estandar
                FROM reserva_habitacion rh
                JOIN habitacion h ON h.id_habitacion = rh.id_habitacion
                JOIN tipo_habitacion th ON th.id_tipo_habitacion = h.id_tipo_habitacion
                WHERE rh.id_reserva = v_reservas(i)
            ) LOOP
                IF detalle.id_alojamiento <> v_alojamiento THEN
                    RAISE_APPLICATION_ERROR(c_error_referencia,
                        'Una habitacion pertenece a otro alojamiento.');
                END IF;
                IF detalle.personas_hospedadas <= 0
                   OR detalle.personas_hospedadas <> TRUNC(detalle.personas_hospedadas) THEN
                    RAISE_APPLICATION_ERROR(c_error_solicitud,
                        'Las personas de cada habitacion deben ser enteras positivas.');
                END IF;
                IF detalle.personas_hospedadas > detalle.capacidad_estandar THEN
                    RAISE_APPLICATION_ERROR(c_error_capacidad,
                        'La capacidad de una habitacion fue excedida.');
                END IF;
            END LOOP;
        END LOOP;
        -- Consulta nueva despues de todos los bloqueos: ve lo confirmado por
        -- otra sesion mientras se esperaba, bajo READ COMMITTED.
        FOR i IN 1 .. v_habitaciones_ordenadas.COUNT LOOP
            SELECT COUNT(*) INTO v_cantidad
            FROM reserva_habitacion primera
            JOIN reserva reserva_primera ON reserva_primera.id_reserva = primera.id_reserva
            JOIN reserva_habitacion segunda
              ON segunda.id_habitacion = primera.id_habitacion
             AND segunda.id_reserva > primera.id_reserva
            JOIN reserva reserva_segunda ON reserva_segunda.id_reserva = segunda.id_reserva
            WHERE primera.id_habitacion = v_habitaciones_ordenadas(i)
              AND reserva_primera.estado <> 'CANCELADA'
              AND reserva_segunda.estado <> 'CANCELADA'
              AND reserva_primera.fecha_checkin < reserva_segunda.fecha_checkout
              AND reserva_segunda.fecha_checkin < reserva_primera.fecha_checkout
              AND ROWNUM = 1;
            IF v_cantidad > 0 THEN
                RAISE_APPLICATION_ERROR(c_error_disponibilidad,
                    'La habitacion tiene reservas no canceladas que se solapan.');
            END IF;
        END LOOP;
    END validar_reservas;

    PROCEDURE sp_crear_reserva(
        p_id_cliente IN NUMBER,
        p_id_alojamiento IN NUMBER,
        p_fecha_in IN DATE,
        p_fecha_out IN DATE,
        p_habitaciones IN lista_solicitudes_habitacion,
        p_servicios IN lista_solicitudes_servicio,
        p_id_reserva OUT NUMBER,
        p_valor_total OUT NUMBER
    ) IS
        v_ids lista_identificadores := lista_identificadores();
        v_ids_ordenados lista_identificadores;
        v_habitaciones lista_habitaciones_capturadas;
        v_servicios lista_servicios_capturados;
        v_indice PLS_INTEGER;
        v_anterior PLS_INTEGER;
        v_num_habitaciones PLS_INTEGER;
        v_num_servicios PLS_INTEGER;
        v_cantidad PLS_INTEGER;
        v_destino NUMBER;
        v_capacidad NUMBER;
        v_estado habitacion.estado%TYPE;
        v_total NUMBER := 0;
        v_id_reserva NUMBER;
        v_posicion PLS_INTEGER := 0;
    BEGIN
        p_id_reserva := NULL;
        p_valor_total := NULL;
        SAVEPOINT turismouq_crear_reserva;
        validar_fechas(p_fecha_in, p_fecha_out);
        SELECT COUNT(*) INTO v_cantidad FROM cliente WHERE id_usuario = p_id_cliente;
        IF v_cantidad <> 1 THEN
            RAISE_APPLICATION_ERROR(c_error_referencia, 'El cliente no existe.');
        END IF;
        SELECT COUNT(*) INTO v_cantidad
        FROM alojamiento WHERE id_alojamiento = p_id_alojamiento;
        IF v_cantidad <> 1 THEN
            RAISE_APPLICATION_ERROR(c_error_referencia, 'El alojamiento no existe.');
        END IF;
        BEGIN
            v_num_habitaciones := p_habitaciones.COUNT;
            v_num_servicios := p_servicios.COUNT;
        EXCEPTION
            WHEN COLLECTION_IS_NULL THEN
                RAISE_APPLICATION_ERROR(c_error_solicitud,
                    'Inicialice las colecciones; servicios admite una coleccion vacia.');
        END;
        IF v_num_habitaciones = 0 THEN
            RAISE_APPLICATION_ERROR(c_error_solicitud,
                'Se requiere al menos una habitacion.');
        END IF;
        v_indice := p_habitaciones.FIRST;
        WHILE v_indice IS NOT NULL LOOP
            IF p_habitaciones(v_indice).id_habitacion IS NULL
               OR p_habitaciones(v_indice).personas_hospedadas IS NULL
               OR p_habitaciones(v_indice).personas_hospedadas <= 0
               OR p_habitaciones(v_indice).personas_hospedadas
                    <> TRUNC(p_habitaciones(v_indice).personas_hospedadas) THEN
                RAISE_APPLICATION_ERROR(c_error_solicitud,
                    'Habitaciones y personas enteras positivas son obligatorias.');
            END IF;
            v_ids.EXTEND;
            v_ids(v_ids.COUNT) := p_habitaciones(v_indice).id_habitacion;
            v_indice := p_habitaciones.NEXT(v_indice);
        END LOOP;
        ordenar_identificadores(v_ids, v_ids_ordenados);
        IF v_ids_ordenados.COUNT <> v_num_habitaciones THEN
            RAISE_APPLICATION_ERROR(c_error_solicitud,
                'La solicitud contiene habitaciones duplicadas.');
        END IF;
        v_indice := p_servicios.FIRST;
        WHILE v_indice IS NOT NULL LOOP
            IF p_servicios(v_indice).id_servicio IS NULL
               OR p_servicios(v_indice).cantidad IS NULL
               OR p_servicios(v_indice).cantidad <= 0
               OR p_servicios(v_indice).cantidad <> TRUNC(p_servicios(v_indice).cantidad)
               OR p_servicios(v_indice).cantidad > 999999 THEN
                RAISE_APPLICATION_ERROR(c_error_solicitud,
                    'Servicios y cantidades enteras positivas representables son obligatorios.');
            END IF;
            v_anterior := p_servicios.FIRST;
            WHILE v_anterior <> v_indice LOOP
                IF p_servicios(v_anterior).id_servicio = p_servicios(v_indice).id_servicio THEN
                    RAISE_APPLICATION_ERROR(c_error_solicitud,
                        'La solicitud contiene servicios duplicados.');
                END IF;
                v_anterior := p_servicios.NEXT(v_anterior);
            END LOOP;
            v_indice := p_servicios.NEXT(v_indice);
        END LOOP;

        FOR i IN 1 .. v_ids_ordenados.COUNT LOOP
            bloquear_identificador('HABITACION', v_ids_ordenados(i));
        END LOOP;
        v_indice := p_habitaciones.FIRST;
        WHILE v_indice IS NOT NULL LOOP
            SELECT h.id_alojamiento, h.estado, th.capacidad_estandar
            INTO v_destino, v_estado, v_capacidad
            FROM habitacion h
            JOIN tipo_habitacion th ON th.id_tipo_habitacion = h.id_tipo_habitacion
            WHERE h.id_habitacion = p_habitaciones(v_indice).id_habitacion;
            IF v_destino <> p_id_alojamiento THEN
                RAISE_APPLICATION_ERROR(c_error_referencia,
                    'La habitacion solicitada pertenece a otro alojamiento.');
            END IF;
            IF v_estado <> 'DISPONIBLE' THEN
                RAISE_APPLICATION_ERROR(c_error_disponibilidad,
                    'La habitacion no esta operativamente disponible.');
            END IF;
            SELECT COUNT(*) INTO v_cantidad
            FROM reserva_habitacion rh JOIN reserva r ON r.id_reserva = rh.id_reserva
            WHERE rh.id_habitacion = p_habitaciones(v_indice).id_habitacion
              AND r.estado <> 'CANCELADA'
              AND r.fecha_checkin < p_fecha_out AND p_fecha_in < r.fecha_checkout
              AND ROWNUM = 1;
            IF v_cantidad > 0 THEN
                RAISE_APPLICATION_ERROR(c_error_disponibilidad,
                    'La habitacion no esta disponible en el intervalo solicitado.');
            END IF;
            IF p_habitaciones(v_indice).personas_hospedadas > v_capacidad THEN
                RAISE_APPLICATION_ERROR(c_error_capacidad,
                    'Las personas exceden la capacidad de la habitacion.');
            END IF;
            v_posicion := v_posicion + 1;
            v_habitaciones(v_posicion).id_habitacion :=
                p_habitaciones(v_indice).id_habitacion;
            v_habitaciones(v_posicion).personas :=
                p_habitaciones(v_indice).personas_hospedadas;
            capturar_tramos(
                p_habitaciones(v_indice).id_habitacion, p_fecha_in, p_fecha_out,
                v_habitaciones(v_posicion).tramos,
                v_habitaciones(v_posicion).importe
            );
            v_total := v_total + v_habitaciones(v_posicion).importe;
            validar_importe(v_total, c_maximo_reserva);
            v_indice := p_habitaciones.NEXT(v_indice);
        END LOOP;
        v_posicion := 0;
        v_indice := p_servicios.FIRST;
        WHILE v_indice IS NOT NULL LOOP
            v_posicion := v_posicion + 1;
            BEGIN
                SELECT id_alojamiento, precio_unitario
                INTO v_destino, v_servicios(v_posicion).precio
                FROM servicio WHERE id_servicio = p_servicios(v_indice).id_servicio;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN
                    RAISE_APPLICATION_ERROR(c_error_servicio, 'El servicio no existe.');
            END;
            IF v_destino <> p_id_alojamiento THEN
                RAISE_APPLICATION_ERROR(c_error_servicio,
                    'El servicio pertenece a otro alojamiento.');
            END IF;
            v_servicios(v_posicion).id_servicio := p_servicios(v_indice).id_servicio;
            v_servicios(v_posicion).cantidad := p_servicios(v_indice).cantidad;
            v_servicios(v_posicion).subtotal := ROUND(
                v_servicios(v_posicion).precio * p_servicios(v_indice).cantidad, 2);
            validar_importe(v_servicios(v_posicion).subtotal, c_maximo_reserva);
            v_total := v_total + v_servicios(v_posicion).subtotal;
            validar_importe(v_total, c_maximo_reserva);
            v_indice := p_servicios.NEXT(v_indice);
        END LOOP;

        INSERT INTO reserva(
            id_cliente, id_alojamiento, fecha_checkin, fecha_checkout, estado, valor_total
        ) VALUES (
            p_id_cliente, p_id_alojamiento, p_fecha_in, p_fecha_out, 'PENDIENTE', v_total
        ) RETURNING id_reserva INTO v_id_reserva;

        FOR i IN 1 .. v_habitaciones.COUNT LOOP
            INSERT INTO reserva_habitacion(
                id_reserva, id_habitacion, personas_hospedadas, precio_estadia_habitacion
            ) VALUES (
                v_id_reserva, v_habitaciones(i).id_habitacion,
                v_habitaciones(i).personas, v_habitaciones(i).importe
            );
            FOR j IN 1 .. v_habitaciones(i).tramos.COUNT LOOP
                INSERT INTO reserva_habitacion_tarifa_aplicada(
                    id_reserva, id_habitacion, fecha_inicio_tramo, fecha_fin_tramo,
                    id_temporada, tipo_temporada_aplicado, precio_noche_aplicado, origen_dato
                ) VALUES (
                    v_id_reserva, v_habitaciones(i).id_habitacion,
                    v_habitaciones(i).tramos(j).fecha_inicio,
                    v_habitaciones(i).tramos(j).fecha_fin,
                    v_habitaciones(i).tramos(j).id_temporada,
                    v_habitaciones(i).tramos(j).tipo_temporada,
                    v_habitaciones(i).tramos(j).precio_noche, 'CAPTURADO'
                );
            END LOOP;
        END LOOP;
        FOR i IN 1 .. v_servicios.COUNT LOOP
            INSERT INTO reserva_servicio(
                id_reserva, id_servicio, cantidad, precio_unitario_aplicado, subtotal
            ) VALUES (
                v_id_reserva, v_servicios(i).id_servicio,
                v_servicios(i).cantidad, v_servicios(i).precio, v_servicios(i).subtotal
            );
        END LOOP;
        p_id_reserva := v_id_reserva;
        p_valor_total := v_total;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK TO turismouq_crear_reserva;
            RAISE;
    END sp_crear_reserva;

    PROCEDURE sp_liquidar_mes(
        p_anio IN NUMBER,
        p_mes IN NUMBER,
        p_porcentaje_comision IN NUMBER,
        p_id_alojamiento IN NUMBER DEFAULT NULL,
        p_liquidaciones_creadas OUT PLS_INTEGER,
        p_liquidaciones_conservadas OUT PLS_INTEGER
    ) IS
        CURSOR cursor_liquidacion_alojamiento(
            p_inicio DATE, p_fin_exclusivo DATE, p_filtro_alojamiento NUMBER
        ) IS
            SELECT a.id_alojamiento,
                   NVL(f.total_hospedaje, 0) AS total_hospedaje,
                   NVL(f.total_servicios, 0) AS total_servicios,
                   NVL(f.cantidad_reservas, 0) AS cantidad_reservas,
                   NVL(f.anomalias, 0) AS anomalias
            FROM alojamiento a
            LEFT JOIN (
                SELECT r.id_alojamiento,
                       SUM(NVL(h.total_hospedaje, 0)) AS total_hospedaje,
                       SUM(NVL(s.total_servicios, 0)) AS total_servicios,
                       COUNT(*) AS cantidad_reservas,
                       SUM(
                           CASE WHEN h.cantidad_habitaciones IS NULL
                                  OR NVL(h.anomalias, 0) > 0
                                  OR NVL(s.anomalias, 0) > 0
                                  OR r.fecha_checkin <> TRUNC(r.fecha_checkin)
                                  OR r.fecha_checkout <> TRUNC(r.fecha_checkout)
                                  OR r.fecha_checkout <= r.fecha_checkin
                                  OR r.valor_total <>
                                      NVL(h.total_hospedaje, 0) + NVL(s.total_servicios, 0)
                                THEN 1 ELSE 0 END
                       ) AS anomalias
                FROM reserva r
                LEFT JOIN (
                    SELECT rh.id_reserva,
                           SUM(rh.precio_estadia_habitacion) AS total_hospedaje,
                           COUNT(*) AS cantidad_habitaciones,
                           SUM(
                               CASE WHEN hab.id_alojamiento <> cab.id_alojamiento
                                      OR tr.inicio IS NULL
                                      OR tr.inicio <> cab.fecha_checkin
                                      OR tr.fin <> cab.fecha_checkout
                                      OR tr.noches <> cab.fecha_checkout - cab.fecha_checkin
                                      OR tr.importe <> rh.precio_estadia_habitacion
                                      OR tr.anomalias > 0
                                    THEN 1 ELSE 0 END
                           ) AS anomalias
                    FROM reserva_habitacion rh
                    JOIN habitacion hab ON hab.id_habitacion = rh.id_habitacion
                    JOIN reserva cab ON cab.id_reserva = rh.id_reserva
                    LEFT JOIN (
                        SELECT id_reserva, id_habitacion,
                               MIN(fecha_inicio_tramo) AS inicio,
                               MAX(fecha_fin_tramo) AS fin,
                               SUM(fecha_fin_tramo - fecha_inicio_tramo) AS noches,
                               SUM((fecha_fin_tramo - fecha_inicio_tramo)
                                   * precio_noche_aplicado) AS importe,
                               SUM(CASE WHEN fecha_inicio_tramo <> TRUNC(fecha_inicio_tramo)
                                          OR fecha_fin_tramo <> TRUNC(fecha_fin_tramo)
                                          OR fecha_fin_tramo <= fecha_inicio_tramo
                                          OR (fin_anterior IS NOT NULL
                                              AND fin_anterior <> fecha_inicio_tramo)
                                        THEN 1 ELSE 0 END) AS anomalias
                        FROM (
                            SELECT t.*,
                                   LAG(fecha_fin_tramo) OVER (
                                       PARTITION BY id_reserva, id_habitacion
                                       ORDER BY fecha_inicio_tramo
                                   ) AS fin_anterior
                            FROM reserva_habitacion_tarifa_aplicada t
                        )
                        GROUP BY id_reserva, id_habitacion
                    ) tr ON tr.id_reserva = rh.id_reserva AND tr.id_habitacion = rh.id_habitacion
                    GROUP BY rh.id_reserva
                ) h ON h.id_reserva = r.id_reserva
                LEFT JOIN (
                    SELECT rs.id_reserva, SUM(rs.subtotal) AS total_servicios,
                           SUM(CASE WHEN ser.id_alojamiento <> cab.id_alojamiento
                                      OR rs.cantidad <= 0 OR rs.cantidad <> TRUNC(rs.cantidad)
                                      OR rs.subtotal <>
                                          ROUND(rs.cantidad * rs.precio_unitario_aplicado, 2)
                                    THEN 1 ELSE 0 END) AS anomalias
                    FROM reserva_servicio rs
                    JOIN servicio ser ON ser.id_servicio = rs.id_servicio
                    JOIN reserva cab ON cab.id_reserva = rs.id_reserva
                    GROUP BY rs.id_reserva
                ) s ON s.id_reserva = r.id_reserva
                WHERE r.estado = 'FINALIZADA'
                  AND r.fecha_checkout >= p_inicio AND r.fecha_checkout < p_fin_exclusivo
                GROUP BY r.id_alojamiento
            ) f ON f.id_alojamiento = a.id_alojamiento
            WHERE (p_filtro_alojamiento IS NULL OR a.id_alojamiento = p_filtro_alojamiento)
              AND (
                  NVL(f.cantidad_reservas, 0) > 0
                  OR EXISTS (
                      SELECT 1 FROM liquidacion_mensual l
                      WHERE l.id_alojamiento = a.id_alojamiento
                        AND l.periodo_anio = EXTRACT(YEAR FROM p_inicio)
                        AND l.periodo_mes = EXTRACT(MONTH FROM p_inicio)
                  )
              )
            ORDER BY a.id_alojamiento;

        v_fila cursor_liquidacion_alojamiento%ROWTYPE;
        v_corte liquidacion_mensual%ROWTYPE;
        v_inicio DATE;
        v_fin DATE;
        v_calendario VARCHAR2(80);
        v_cantidad PLS_INTEGER;
        v_base NUMBER;
        v_comision NUMBER;
        v_neto NUMBER;
        v_existe BOOLEAN;
    BEGIN
        p_liquidaciones_creadas := 0;
        p_liquidaciones_conservadas := 0;
        SAVEPOINT turismouq_liquidar_mes;
        IF p_anio IS NULL OR p_anio <> TRUNC(p_anio) OR p_anio < 2000 OR p_anio > 9999
           OR p_mes IS NULL OR p_mes <> TRUNC(p_mes) OR p_mes < 1 OR p_mes > 12
           OR (p_anio = 9999 AND p_mes = 12)
           OR p_porcentaje_comision IS NULL OR p_porcentaje_comision < 0
           OR p_porcentaje_comision > 100
           OR p_porcentaje_comision <> ROUND(p_porcentaje_comision, 4) THEN
            RAISE_APPLICATION_ERROR(c_error_periodo,
                'Periodo invalido o comision obligatoria entre 0 y 100 con hasta cuatro decimales.');
        END IF;
        SELECT "VALUE" INTO v_calendario FROM nls_session_parameters
        WHERE parameter = 'NLS_CALENDAR';
        IF UPPER(v_calendario) <> 'GREGORIAN' THEN
            RAISE_APPLICATION_ERROR(c_error_periodo,
                'Configure NLS_CALENDAR=GREGORIAN en esta conexion antes de liquidar.');
        END IF;
        v_inicio := TO_DATE(
            TO_CHAR(p_anio, 'FM0000') || TO_CHAR(p_mes, 'FM00') || '01', 'FXYYYYMMDD');
        v_fin := ADD_MONTHS(v_inicio, 1);
        IF p_id_alojamiento IS NOT NULL THEN
            SELECT COUNT(*) INTO v_cantidad
            FROM alojamiento WHERE id_alojamiento = p_id_alojamiento;
            IF v_cantidad <> 1 THEN
                RAISE_APPLICATION_ERROR(c_error_referencia, 'El alojamiento no existe.');
            END IF;
        END IF;
        SELECT COUNT(*) INTO v_cantidad FROM reserva
        WHERE estado = 'FINALIZADA'
          AND fecha_checkout >= v_inicio AND fecha_checkout < v_fin
          AND id_alojamiento IS NULL;
        IF v_cantidad > 0 AND p_id_alojamiento IS NULL THEN
            RAISE_APPLICATION_ERROR(c_error_integridad,
                'La poblacion de liquidacion contiene reservas sin alojamiento.');
        END IF;
        -- Se bloquea el padre antes de abrir la consulta financiera. Dos cortes
        -- del mismo alojamiento quedan serializados, incluso si son de otro mes.
        FOR objetivo IN (
            SELECT id_alojamiento FROM alojamiento
            WHERE p_id_alojamiento IS NULL OR id_alojamiento = p_id_alojamiento
            ORDER BY id_alojamiento
        ) LOOP
            bloquear_identificador('ALOJAMIENTO', objetivo.id_alojamiento);
        END LOOP;
        OPEN cursor_liquidacion_alojamiento(v_inicio, v_fin, p_id_alojamiento);
        LOOP
            FETCH cursor_liquidacion_alojamiento INTO v_fila;
            EXIT WHEN cursor_liquidacion_alojamiento%NOTFOUND;
            IF v_fila.anomalias > 0 THEN
                RAISE_APPLICATION_ERROR(c_error_integridad,
                    'La poblacion de liquidacion tiene importes, alojamiento o tramos incoherentes.');
            END IF;
            validar_importe(v_fila.total_hospedaje, c_maximo_liquidacion);
            validar_importe(v_fila.total_servicios, c_maximo_liquidacion);
            v_base := v_fila.total_hospedaje + v_fila.total_servicios;
            validar_importe(v_base, c_maximo_liquidacion);
            v_comision := ROUND(v_base * p_porcentaje_comision / 100, 2);
            v_neto := v_base - v_comision;
            validar_importe(v_comision, c_maximo_liquidacion);
            validar_importe(v_neto, c_maximo_liquidacion);
            v_existe := TRUE;
            BEGIN
                SELECT * INTO v_corte FROM liquidacion_mensual
                WHERE id_alojamiento = v_fila.id_alojamiento
                  AND periodo_anio = p_anio AND periodo_mes = p_mes
                FOR UPDATE WAIT 5;
            EXCEPTION
                WHEN NO_DATA_FOUND THEN v_existe := FALSE;
                WHEN OTHERS THEN
                    IF SQLCODE IN (-30006, -54) THEN
                        RAISE_APPLICATION_ERROR(c_error_bloqueo,
                            'El corte mensual esta bloqueado temporalmente.');
                    END IF;
                    RAISE;
            END;
            IF NOT v_existe THEN
                IF v_fila.cantidad_reservas > 0 THEN
                    INSERT INTO liquidacion_mensual(
                        id_alojamiento, periodo_anio, periodo_mes,
                        total_hospedaje, total_servicios, comision_plataforma,
                        neto_propietario, estado, porcentaje_comision,
                        base_comision, criterio_liquidacion
                    ) VALUES (
                        v_fila.id_alojamiento, p_anio, p_mes,
                        v_fila.total_hospedaje, v_fila.total_servicios, v_comision,
                        v_neto, 'CALCULADA', p_porcentaje_comision,
                        v_base, c_criterio_liquidacion
                    );
                    p_liquidaciones_creadas := p_liquidaciones_creadas + 1;
                END IF;
            ELSE
                IF v_corte.porcentaje_comision IS NULL OR v_corte.base_comision IS NULL
                   OR v_corte.criterio_liquidacion IS NULL THEN
                    RAISE_APPLICATION_ERROR(c_error_corte_legado,
                        'El corte previo no tiene metadatos verificables de comision y criterio.');
                END IF;
                IF v_corte.total_hospedaje = v_fila.total_hospedaje
                   AND v_corte.total_servicios = v_fila.total_servicios
                   AND v_corte.comision_plataforma = v_comision
                   AND v_corte.neto_propietario = v_neto
                   AND v_corte.porcentaje_comision = p_porcentaje_comision
                   AND v_corte.base_comision = v_base
                   AND v_corte.criterio_liquidacion = c_criterio_liquidacion THEN
                    p_liquidaciones_conservadas := p_liquidaciones_conservadas + 1;
                ELSIF v_corte.estado IN ('DISPERSADA', 'PAGADA') THEN
                    RAISE_APPLICATION_ERROR(c_error_corte_cerrado,
                        'El corte cerrado difiere de la fuente o politica; no se sobrescribe.');
                ELSE
                    RAISE_APPLICATION_ERROR(c_error_corte_calculado,
                        'El corte calculado difiere; requiere un recalculo explicito fuera de esta operacion.');
                END IF;
            END IF;
        END LOOP;
        CLOSE cursor_liquidacion_alojamiento;
    EXCEPTION
        WHEN OTHERS THEN
            IF cursor_liquidacion_alojamiento%ISOPEN THEN
                CLOSE cursor_liquidacion_alojamiento;
            END IF;
            ROLLBACK TO turismouq_liquidar_mes;
            RAISE;
    END sp_liquidar_mes;
END pkg_turismouq;
/
