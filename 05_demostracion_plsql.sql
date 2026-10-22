-- TURISMOUQ - Demostracion transaccional de Entrega 2.
-- SQL*Plus / SQLcl; iniciar el cliente desde la raiz del repositorio.
-- Precondiciones de la CONEXION antes de este archivo:
--   ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED;
--   ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
-- Conectar al propietario aislado de E2, con datos sinteticos y paquete/triggers
-- instalados. No ejecutar con transacciones propias pendientes.
-- No contiene DDL, COMMIT, cambio de usuario ni contrasenas.
-- Todos los cambios se revierten al savepoint; IDENTITY puede consumir IDs.
SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON SIZE UNLIMITED
SET VERIFY OFF
SET FEEDBACK ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE

DECLARE
    v_usuario VARCHAR2(128) := SYS_CONTEXT('USERENV', 'SESSION_USER');
    v_esquema VARCHAR2(128) := SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA');
    v_calendario VARCHAR2(80);
    v_cantidad PLS_INTEGER;
BEGIN
    IF v_usuario IN ('SYS', 'SYSTEM', 'TURISMOUQ', 'TURISMOUQ_E1')
       OR v_usuario <> v_esquema THEN
        RAISE_APPLICATION_ERROR(-20980,
            'Demostracion rechazada: conecte al propietario aislado de E2; no use los esquemas originales.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_tables
    WHERE table_name IN (
        'USUARIO_SISTEMA', 'PROPIETARIO', 'CLIENTE', 'MUNICIPIO',
        'TIPO_ALOJAMIENTO', 'ALOJAMIENTO', 'TIPO_HABITACION', 'HABITACION',
        'COMODIDAD', 'ALOJAMIENTO_COMODIDAD', 'TEMPORADA', 'TARIFA',
        'AUDITORIA_TARIFA', 'RESERVA', 'RESERVA_HABITACION', 'PAGO',
        'SERVICIO', 'RESERVA_SERVICIO', 'RESENA', 'LIQUIDACION_MENSUAL',
        'HISTORICO_RESERVA', 'RESERVA_HABITACION_TARIFA_APLICADA'
    );
    IF v_cantidad <> 22 THEN
        RAISE_APPLICATION_ERROR(-20981, 'Se requieren las 22 tablas propias del modelo E2.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_objects
    WHERE object_name = 'PKG_TURISMOUQ'
      AND object_type IN ('PACKAGE', 'PACKAGE BODY') AND status = 'VALID';
    IF v_cantidad <> 2 THEN
        RAISE_APPLICATION_ERROR(-20981, 'El paquete y su cuerpo deben estar VALID.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_triggers
    WHERE trigger_name IN ('TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA')
      AND status = 'ENABLED';
    IF v_cantidad <> 3 THEN
        RAISE_APPLICATION_ERROR(-20981, 'Instale y habilite los tres triggers E2 antes de demostrar.');
    END IF;
    SELECT "VALUE" INTO v_calendario FROM nls_session_parameters
    WHERE parameter = 'NLS_CALENDAR';
    IF v_calendario <> 'GREGORIAN' THEN
        RAISE_APPLICATION_ERROR(-20981,
            'Configure NLS_CALENDAR=GREGORIAN antes de ejecutar la demostracion.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('PROPIETARIO=' || v_usuario || '; ESQUEMA=' || v_esquema);
    DBMS_OUTPUT.PUT_LINE('Preparacion comprobada: 22 tablas, paquete VALID y tres triggers habilitados.');
END;
/

DECLARE
    c_entrada CONSTANT DATE := DATE '2027-01-14';
    c_salida CONSTANT DATE := DATE '2027-01-16';
    c_porcentaje_prueba CONSTANT NUMBER := 12;
    v_habitaciones pkg_turismouq.lista_solicitudes_habitacion :=
        pkg_turismouq.lista_solicitudes_habitacion();
    v_servicios pkg_turismouq.lista_solicitudes_servicio :=
        pkg_turismouq.lista_solicitudes_servicio();
    v_id_habitacion NUMBER;
    v_id_alojamiento NUMBER;
    v_capacidad NUMBER;
    v_id_cliente NUMBER;
    v_id_reserva NUMBER;
    v_total NUMBER;
    v_cotizacion NUMBER;
    v_id_tarifa NUMBER;
    v_precio NUMBER;
    v_precio_observado NUMBER;
    v_eventos_antes NUMBER;
    v_eventos_despues NUMBER;
    v_eventos_totales_antes NUMBER;
    v_reservas_antes NUMBER;
    v_liquidaciones_antes NUMBER;
    v_cantidad NUMBER;
    v_anio NUMBER := 2025;
    v_mes NUMBER;
    v_alojamiento_liquidacion NUMBER;
    v_creadas PLS_INTEGER;
    v_conservadas PLS_INTEGER;
    v_corte liquidacion_mensual%ROWTYPE;
    v_id_corte NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_reservas_antes FROM reserva;
    SELECT COUNT(*) INTO v_eventos_totales_antes FROM auditoria_tarifa;
    SELECT COUNT(*) INTO v_liquidaciones_antes FROM liquidacion_mensual;
    SAVEPOINT turismo_demo_entrega2;

    BEGIN
        SELECT id_habitacion, id_alojamiento, capacidad_estandar
        INTO v_id_habitacion, v_id_alojamiento, v_capacidad
        FROM (
            SELECT h.id_habitacion, h.id_alojamiento, th.capacidad_estandar
            FROM habitacion h
            JOIN tipo_habitacion th ON th.id_tipo_habitacion = h.id_tipo_habitacion
            WHERE h.estado = 'DISPONIBLE'
              AND NOT EXISTS (
                  SELECT 1 FROM reserva_habitacion rh
                  JOIN reserva r ON r.id_reserva = rh.id_reserva
                  WHERE rh.id_habitacion = h.id_habitacion
                    AND r.estado <> 'CANCELADA'
                    AND r.fecha_checkin < c_salida AND c_entrada < r.fecha_checkout
              )
            ORDER BY h.id_habitacion
        )
        WHERE ROWNUM = 1;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20982,
                'No hay habitacion libre para 2027-01-14 a 2027-01-16 en este conjunto.');
    END;
    SELECT MIN(id_usuario) INTO v_id_cliente FROM cliente;
    IF v_id_cliente IS NULL THEN
        RAISE_APPLICATION_ERROR(-20982, 'Cargue los clientes del conjunto academico.');
    END IF;
    SELECT pkg_turismouq.fn_valor_estadia(v_id_habitacion, c_entrada, c_salida)
    INTO v_cotizacion FROM dual;
    DBMS_OUTPUT.PUT_LINE('COTIZACION: habitacion=' || v_id_habitacion
        || '; noches=2; entrada=2027-01-14; salida_exclusiva=2027-01-16; valor='
        || TO_CHAR(v_cotizacion));

    v_habitaciones.EXTEND;
    v_habitaciones(1).id_habitacion := v_id_habitacion;
    v_habitaciones(1).personas_hospedadas := 1;

    BEGIN
        pkg_turismouq.sp_crear_reserva(
            v_id_cliente, v_id_alojamiento, c_entrada, c_entrada,
            v_habitaciones, v_servicios, v_id_reserva, v_total);
        RAISE_APPLICATION_ERROR(-20983, 'Fallo de demostracion: se acepto checkout igual al check-in.');
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLCODE <> pkg_turismouq.c_error_checkout THEN RAISE; END IF;
            DBMS_OUTPUT.PUT_LINE('ERROR ESPERADO checkout: ' || SQLCODE || ' ' || SQLERRM);
    END;

    v_habitaciones(1).personas_hospedadas := v_capacidad + 1;
    BEGIN
        pkg_turismouq.sp_crear_reserva(
            v_id_cliente, v_id_alojamiento, c_entrada, c_salida,
            v_habitaciones, v_servicios, v_id_reserva, v_total);
        RAISE_APPLICATION_ERROR(-20983, 'Fallo de demostracion: se acepto capacidad excedida.');
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLCODE <> pkg_turismouq.c_error_capacidad THEN RAISE; END IF;
            DBMS_OUTPUT.PUT_LINE('ERROR ESPERADO capacidad: ' || SQLCODE || ' ' || SQLERRM);
    END;
    v_habitaciones(1).personas_hospedadas := 1;

    pkg_turismouq.sp_crear_reserva(
        v_id_cliente, v_id_alojamiento, c_entrada, c_salida,
        v_habitaciones, v_servicios, v_id_reserva, v_total);
    IF v_total <> v_cotizacion THEN
        RAISE_APPLICATION_ERROR(-20983, 'La reserva no coincide con la cotizacion capturada.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('RESERVA CREADA SIN CONFIRMAR: id=' || v_id_reserva
        || '; estado=PENDIENTE; total=' || TO_CHAR(v_total));

    BEGIN
        pkg_turismouq.sp_crear_reserva(
            v_id_cliente, v_id_alojamiento, c_entrada, c_salida,
            v_habitaciones, v_servicios, v_id_reserva, v_total);
        RAISE_APPLICATION_ERROR(-20983, 'Fallo de demostracion: se acepto una reserva solapada.');
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLCODE <> pkg_turismouq.c_error_disponibilidad THEN RAISE; END IF;
            DBMS_OUTPUT.PUT_LINE('ERROR ESPERADO solape: ' || SQLCODE || ' ' || SQLERRM);
    END;

    SELECT id_tarifa, precio_noche INTO v_id_tarifa, v_precio
    FROM tarifa ta JOIN temporada t ON t.id_temporada = ta.id_temporada
    WHERE ta.id_habitacion = v_id_habitacion
      AND t.fecha_inicio <= c_entrada AND t.fecha_fin >= c_entrada;
    SELECT COUNT(*) INTO v_eventos_antes FROM auditoria_tarifa WHERE id_tarifa = v_id_tarifa;
    SAVEPOINT turismo_demo_precio;
    UPDATE tarifa SET precio_noche = v_precio + 1 WHERE id_tarifa = v_id_tarifa;
    SELECT COUNT(*) INTO v_eventos_despues FROM auditoria_tarifa WHERE id_tarifa = v_id_tarifa;
    IF v_eventos_despues <> v_eventos_antes + 1 THEN
        RAISE_APPLICATION_ERROR(-20984, 'El UPDATE no genero exactamente un evento de auditoria.');
    END IF;
    FOR evento IN (
        SELECT usuario_oracle, fecha_cambio, precio_anterior, precio_nuevo,
               RAWTOHEX(id_sentencia) AS sentencia
        FROM auditoria_tarifa
        WHERE id_tarifa = v_id_tarifa
          AND precio_anterior = v_precio AND precio_nuevo = v_precio + 1
          AND usuario_oracle = SYS_CONTEXT('USERENV', 'SESSION_USER')
        ORDER BY id_auditoria DESC
        FETCH FIRST 1 ROW ONLY
    ) LOOP
        DBMS_OUTPUT.PUT_LINE('AUDITORIA: actor=' || evento.usuario_oracle
            || '; fecha_UTC=' || TO_CHAR(evento.fecha_cambio, 'YYYY-MM-DD HH24:MI:SS.FF6')
            || '; anterior=' || TO_CHAR(evento.precio_anterior)
            || '; nuevo=' || TO_CHAR(evento.precio_nuevo)
            || '; sentencia=' || evento.sentencia);
    END LOOP;
    ROLLBACK TO turismo_demo_precio;
    SELECT precio_noche INTO v_precio_observado FROM tarifa WHERE id_tarifa = v_id_tarifa;
    SELECT COUNT(*) INTO v_eventos_despues FROM auditoria_tarifa WHERE id_tarifa = v_id_tarifa;
    IF v_precio_observado <> v_precio OR v_eventos_despues <> v_eventos_antes THEN
        RAISE_APPLICATION_ERROR(-20984, 'El rollback no restauro tarifa y auditoria.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('ROLLBACK DE PRECIO: tarifa y auditoria restauradas.');

    BEGIN
        SELECT mes, id_alojamiento INTO v_mes, v_alojamiento_liquidacion
        FROM (
            SELECT EXTRACT(MONTH FROM r.fecha_checkout) AS mes, r.id_alojamiento
            FROM reserva r
            WHERE r.estado = 'FINALIZADA'
              AND r.fecha_checkout >= DATE '2025-01-01'
              AND r.fecha_checkout < DATE '2026-01-01'
              AND NOT EXISTS (
                  SELECT 1 FROM liquidacion_mensual l
                  WHERE l.id_alojamiento = r.id_alojamiento AND l.periodo_anio = 2025
                    AND l.periodo_mes = EXTRACT(MONTH FROM r.fecha_checkout)
              )
            GROUP BY EXTRACT(MONTH FROM r.fecha_checkout), r.id_alojamiento
            ORDER BY mes, r.id_alojamiento
        )
        WHERE ROWNUM = 1;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20985,
                'No hay alojamiento/mes 2025 con finalizadas y sin corte previo; use el esquema academico nuevo.');
    END;
    pkg_turismouq.sp_liquidar_mes(
        v_anio, v_mes, c_porcentaje_prueba, v_alojamiento_liquidacion,
        v_creadas, v_conservadas);
    IF v_creadas <> 1 OR v_conservadas <> 0 THEN
        RAISE_APPLICATION_ERROR(-20985, 'La primera liquidacion debe crear exactamente un corte.');
    END IF;
    SELECT * INTO v_corte FROM liquidacion_mensual
    WHERE id_alojamiento = v_alojamiento_liquidacion
      AND periodo_anio = v_anio AND periodo_mes = v_mes;
    v_id_corte := v_corte.id_liquidacion;
    DBMS_OUTPUT.PUT_LINE('LIQUIDACION SIN CONFIRMAR: alojamiento=' || v_alojamiento_liquidacion
        || '; anio=' || v_anio || '; mes=' || v_mes
        || '; porcentaje_de_prueba=12; H=' || TO_CHAR(v_corte.total_hospedaje)
        || '; S=' || TO_CHAR(v_corte.total_servicios)
        || '; base=' || TO_CHAR(v_corte.base_comision)
        || '; comision=' || TO_CHAR(v_corte.comision_plataforma)
        || '; neto=' || TO_CHAR(v_corte.neto_propietario));
    pkg_turismouq.sp_liquidar_mes(
        v_anio, v_mes, c_porcentaje_prueba, v_alojamiento_liquidacion,
        v_creadas, v_conservadas);
    IF v_creadas <> 0 OR v_conservadas <> 1 THEN
        RAISE_APPLICATION_ERROR(-20985, 'La repeticion debe conservar el mismo corte sin DML.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM liquidacion_mensual
    WHERE id_liquidacion = v_id_corte AND id_alojamiento = v_alojamiento_liquidacion
      AND periodo_anio = v_anio AND periodo_mes = v_mes;
    IF v_cantidad <> 1 THEN
        RAISE_APPLICATION_ERROR(-20985, 'La repeticion cambio la identidad del corte.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('IDEMPOTENCIA: segunda llamada crea=0, conserva=1; mismo ID=' || v_id_corte);

    ROLLBACK TO turismo_demo_entrega2;
    SELECT COUNT(*) INTO v_cantidad FROM reserva;
    IF v_cantidad <> v_reservas_antes THEN
        RAISE_APPLICATION_ERROR(-20986, 'Quedaron reservas de demostracion.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM auditoria_tarifa;
    IF v_cantidad <> v_eventos_totales_antes THEN
        RAISE_APPLICATION_ERROR(-20986, 'Quedaron eventos de auditoria de demostracion.');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM liquidacion_mensual;
    IF v_cantidad <> v_liquidaciones_antes THEN
        RAISE_APPLICATION_ERROR(-20986, 'Quedaron liquidaciones de demostracion.');
    END IF;
    DBMS_OUTPUT.PUT_LINE('DEMOSTRACION APROBADA: rollback final; conteos de reservas, auditoria y liquidaciones restaurados.');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO turismo_demo_entrega2;
        RAISE;
END;
/

SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'PKG_TURISMOUQ', 'TRG_AUDITAR_TARIFA', 'TRG_RESERVA_HABITACION', 'TRG_RESERVA'
)
ORDER BY object_type, object_name;
