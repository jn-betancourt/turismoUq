-- TURISMOUQ - Entrega 2. Contrato publico del paquete.
SET DEFINE OFF
SET SQLBLANKLINES ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE PACKAGE pkg_turismouq AUTHID DEFINER AS
    c_error_checkout CONSTANT PLS_INTEGER := -20301;
    c_error_fechas CONSTANT PLS_INTEGER := -20302;
    c_error_habitacion CONSTANT PLS_INTEGER := -20303;
    c_error_disponibilidad CONSTANT PLS_INTEGER := -20304;
    c_error_capacidad CONSTANT PLS_INTEGER := -20305;
    c_error_referencia CONSTANT PLS_INTEGER := -20306;
    c_error_solicitud CONSTANT PLS_INTEGER := -20307;
    c_error_cobertura CONSTANT PLS_INTEGER := -20308;
    c_error_temporadas CONSTANT PLS_INTEGER := -20309;
    c_error_tarifa CONSTANT PLS_INTEGER := -20310;
    c_error_importe CONSTANT PLS_INTEGER := -20311;
    c_error_bloqueo CONSTANT PLS_INTEGER := -20312;
    c_error_servicio CONSTANT PLS_INTEGER := -20313;
    c_error_integridad CONSTANT PLS_INTEGER := -20314;
    c_error_periodo CONSTANT PLS_INTEGER := -20320;
    c_error_corte_calculado CONSTANT PLS_INTEGER := -20321;
    c_error_corte_cerrado CONSTANT PLS_INTEGER := -20322;
    c_error_corte_legado CONSTANT PLS_INTEGER := -20323;
    c_espera_bloqueo_segundos CONSTANT PLS_INTEGER := 5;
    c_criterio_liquidacion CONSTANT VARCHAR2(40) := 'FINALIZADA_CHECKOUT_HMAS_SERV_V1';

    error_checkout EXCEPTION;
    PRAGMA EXCEPTION_INIT(error_checkout, -20301);
    error_disponibilidad EXCEPTION;
    PRAGMA EXCEPTION_INIT(error_disponibilidad, -20304);
    error_capacidad EXCEPTION;
    PRAGMA EXCEPTION_INIT(error_capacidad, -20305);

    TYPE tipo_solicitud_habitacion IS RECORD (
        id_habitacion NUMBER,
        personas_hospedadas NUMBER
    );
    TYPE lista_solicitudes_habitacion IS TABLE OF tipo_solicitud_habitacion;

    TYPE tipo_solicitud_servicio IS RECORD (
        id_servicio NUMBER,
        cantidad NUMBER
    );
    TYPE lista_solicitudes_servicio IS TABLE OF tipo_solicitud_servicio;
    TYPE lista_identificadores IS TABLE OF NUMBER;

    FUNCTION fn_valor_estadia(
        p_id_habitacion IN NUMBER,
        p_fecha_in IN DATE,
        p_fecha_out IN DATE
    ) RETURN NUMBER;

    -- p_servicios debe ser una coleccion inicializada, vacia si no hay servicios.
    -- Las salidas solo son validas al regresar sin excepcion.
    PROCEDURE sp_crear_reserva(
        p_id_cliente IN NUMBER,
        p_id_alojamiento IN NUMBER,
        p_fecha_in IN DATE,
        p_fecha_out IN DATE,
        p_habitaciones IN lista_solicitudes_habitacion,
        p_servicios IN lista_solicitudes_servicio,
        p_id_reserva OUT NUMBER,
        p_valor_total OUT NUMBER
    );

    PROCEDURE sp_liquidar_mes(
        p_anio IN NUMBER,
        p_mes IN NUMBER,
        p_porcentaje_comision IN NUMBER,
        p_id_alojamiento IN NUMBER DEFAULT NULL,
        p_liquidaciones_creadas OUT PLS_INTEGER,
        p_liquidaciones_conservadas OUT PLS_INTEGER
    );

    -- Para AFTER STATEMENT de los triggers compuestos. No contiene controles
    -- transaccionales ni escribe tablas: bloquea y valida el estado completo.
    -- Se bloquean cabeceras primero y habitaciones despues, en orden numerico.
    PROCEDURE validar_reservas(
        p_ids_reserva IN lista_identificadores,
        p_ids_habitacion_adicionales IN lista_identificadores
            DEFAULT lista_identificadores()
    );
END pkg_turismouq;
/
