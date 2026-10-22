-- Soporte estructural de Entrega 2 sobre el modelo de 22 tablas de Entrega 1.
-- Ejecutar como propietario, despues de 001_tramos_tarifarios.sql si procede,
-- con respaldo y sin trabajo transaccional pendiente. No ejecutar como SYS.
-- Conserva filas existentes: no atribuye porcentajes, criterios, fechas UTC
-- ni identificadores de sentencia al legado. No instala paquetes ni triggers.
-- Es repetible si tipos y restricciones coinciden; falla ante incompatibilidad.
-- El DDL confirma transacciones y no se revierte con un ROLLBACK final.
SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE

DECLARE
    c_regla_porcentaje CONSTANT VARCHAR2(4000) :=
        'porcentaje_comision BETWEEN 0 AND 100';
    c_regla_metadatos CONSTANT VARCHAR2(4000) :=
        '(porcentaje_comision IS NULL
          AND base_comision IS NULL
          AND criterio_liquidacion IS NULL)
         OR
         (porcentaje_comision IS NOT NULL
          AND base_comision IS NOT NULL
          AND criterio_liquidacion IS NOT NULL
          AND TRIM(criterio_liquidacion) IS NOT NULL)';
    c_regla_base CONSTANT VARCHAR2(4000) :=
        'base_comision IS NULL
         OR (base_comision >= 0
             AND base_comision = total_hospedaje + total_servicios)';
    c_regla_comision CONSTANT VARCHAR2(4000) :=
        'porcentaje_comision IS NULL
         OR comision_plataforma =
             ROUND(base_comision * porcentaje_comision / 100, 2)';
    v_cantidad PLS_INTEGER;
    v_longitud_usuario PLS_INTEGER;
    v_metadatos_presentes PLS_INTEGER := 0;
    v_predicado_parcial VARCHAR2(4000);

    FUNCTION existe_columna(p_tabla VARCHAR2, p_columna VARCHAR2) RETURN BOOLEAN IS
        v_coincidencias PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias FROM user_tab_columns
        WHERE table_name = p_tabla AND column_name = p_columna;
        RETURN v_coincidencias = 1;
    END;

    PROCEDURE exigir_columna(
        p_tabla VARCHAR2,
        p_columna VARCHAR2,
        p_tipo VARCHAR2,
        p_nullable VARCHAR2,
        p_precision NUMBER DEFAULT NULL,
        p_escala NUMBER DEFAULT NULL,
        p_longitud NUMBER DEFAULT NULL
    ) IS
        v_coincidencias PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias FROM user_tab_columns
        WHERE table_name = p_tabla AND column_name = p_columna
          AND data_type = p_tipo AND nullable = p_nullable
          AND (p_tipo <> 'NUMBER'
               OR ((data_precision = p_precision
                    OR (data_precision IS NULL AND p_precision IS NULL))
                   AND (data_scale = p_escala
                        OR (data_scale IS NULL AND p_escala IS NULL))))
          AND (p_longitud IS NULL
               OR (p_tipo = 'VARCHAR2' AND char_length = p_longitud)
               OR (p_tipo = 'RAW' AND data_length = p_longitud));
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20401,
                'Columna ausente o incompatible: ' || p_tabla || '.' || p_columna);
        END IF;
    END;

    PROCEDURE exigir_sin_default(p_tabla VARCHAR2, p_columna VARCHAR2) IS
        v_coincidencias PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias FROM user_tab_columns
        WHERE table_name = p_tabla AND column_name = p_columna
          AND default_length IS NULL;
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20402,
                'La procedencia desconocida debe conservarse sin default: '
                || p_tabla || '.' || p_columna);
        END IF;
    END;

    PROCEDURE exigir_restriccion(
        p_tabla VARCHAR2,
        p_nombre VARCHAR2,
        p_tipo VARCHAR2,
        p_condicion VARCHAR2 DEFAULT NULL
    ) IS
        v_coincidencias PLS_INTEGER;
        v_condicion VARCHAR2(4000);
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias FROM user_constraints
        WHERE table_name = p_tabla AND constraint_name = p_nombre
          AND constraint_type = p_tipo AND status = 'ENABLED'
          AND validated = 'VALIDATED' AND deferrable = 'NOT DEFERRABLE';
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20403,
                'Restriccion ausente, incompatible o sin validar: ' || p_nombre);
        END IF;
        IF p_condicion IS NOT NULL THEN
            SELECT search_condition_vc INTO v_condicion FROM user_constraints
            WHERE constraint_name = p_nombre;
            IF v_condicion IS NULL
               OR REGEXP_REPLACE(UPPER(v_condicion), '[[:space:]"]', '') <>
                  REGEXP_REPLACE(UPPER(p_condicion), '[[:space:]"]', '') THEN
                RAISE_APPLICATION_ERROR(-20404,
                    'Condicion incompatible en ' || p_nombre);
            END IF;
        END IF;
    END;

    PROCEDURE exigir_columnas_llave(
        p_nombre VARCHAR2,
        p_columnas VARCHAR2
    ) IS
        v_columnas VARCHAR2(4000);
    BEGIN
        SELECT LISTAGG(column_name, ',') WITHIN GROUP (ORDER BY position)
        INTO v_columnas FROM user_cons_columns
        WHERE constraint_name = p_nombre;
        IF v_columnas IS NULL OR v_columnas <> p_columnas THEN
            RAISE_APPLICATION_ERROR(-20411,
                'Columnas incompatibles en ' || p_nombre);
        END IF;
    END;

    PROCEDURE exigir_destino_fk(
        p_nombre VARCHAR2,
        p_tabla_padre VARCHAR2,
        p_columnas_padre VARCHAR2
    ) IS
        v_coincidencias PLS_INTEGER;
        v_columnas VARCHAR2(4000);
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias
        FROM user_constraints hija
        JOIN user_constraints padre ON padre.constraint_name = hija.r_constraint_name
        WHERE hija.constraint_name = p_nombre
          AND hija.r_owner = SYS_CONTEXT('USERENV', 'SESSION_USER')
          AND hija.delete_rule = 'NO ACTION'
          AND padre.table_name = p_tabla_padre
          AND padre.constraint_type IN ('P', 'U')
          AND padre.status = 'ENABLED' AND padre.validated = 'VALIDATED';
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20412,
                'Destino o regla de borrado incompatibles: ' || p_nombre);
        END IF;
        SELECT LISTAGG(columna.column_name, ',')
               WITHIN GROUP (ORDER BY columna.position)
        INTO v_columnas
        FROM user_cons_columns columna
        JOIN user_constraints hija ON hija.r_constraint_name = columna.constraint_name
        WHERE hija.constraint_name = p_nombre;
        IF v_columnas IS NULL OR v_columnas <> p_columnas_padre THEN
            RAISE_APPLICATION_ERROR(-20413,
                'Columnas de destino incompatibles: ' || p_nombre);
        END IF;
    END;

    PROCEDURE revisar_check_existente(p_nombre VARCHAR2, p_condicion VARCHAR2) IS
        v_coincidencias PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias FROM user_constraints
        WHERE constraint_name = p_nombre;
        IF v_coincidencias > 0 THEN
            exigir_restriccion('LIQUIDACION_MENSUAL', p_nombre, 'C', p_condicion);
        END IF;
    END;

    PROCEDURE crear_check_si_falta(p_nombre VARCHAR2, p_condicion VARCHAR2) IS
        v_coincidencias PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias FROM user_constraints
        WHERE constraint_name = p_nombre;
        IF v_coincidencias = 0 THEN
            -- Nombres y expresiones constantes de esta migracion, sin entrada externa.
            EXECUTE IMMEDIATE 'ALTER TABLE liquidacion_mensual ADD CONSTRAINT '
                || p_nombre || ' CHECK (' || p_condicion || ') ENABLE VALIDATE';
            DBMS_OUTPUT.PUT_LINE('Creada ' || p_nombre);
        END IF;
        exigir_restriccion('LIQUIDACION_MENSUAL', p_nombre, 'C', p_condicion);
    END;
BEGIN
    IF SYS_CONTEXT('USERENV', 'SESSION_USER') IN ('SYS', 'SYSTEM') THEN
        RAISE_APPLICATION_ERROR(-20400,
            'Ejecute la migracion con el propietario del proyecto.');
    END IF;

    SELECT COUNT(*) INTO v_cantidad FROM user_tables
    WHERE table_name IN ('AUDITORIA_TARIFA', 'LIQUIDACION_MENSUAL',
                         'RESERVA_HABITACION_TARIFA_APLICADA');
    IF v_cantidad <> 3 THEN
        RAISE_APPLICATION_ERROR(-20405,
            'Se requiere Entrega 1 con las 22 tablas y soporte de tramos.');
    END IF;

    -- Preflight completo antes del primer ALTER: preservar el contrato base.
    exigir_columna('AUDITORIA_TARIFA', 'ID_AUDITORIA', 'NUMBER', 'N');
    exigir_columna('AUDITORIA_TARIFA', 'ID_TARIFA', 'NUMBER', 'N');
    exigir_columna('AUDITORIA_TARIFA', 'FECHA_CAMBIO', 'TIMESTAMP(6)', 'N');
    exigir_columna('AUDITORIA_TARIFA', 'PRECIO_ANTERIOR', 'NUMBER', 'N', 12, 2);
    exigir_columna('AUDITORIA_TARIFA', 'PRECIO_NUEVO', 'NUMBER', 'N', 12, 2);
    exigir_columna('AUDITORIA_TARIFA', 'OPERACION', 'VARCHAR2', 'N', p_longitud => 6);
    SELECT COUNT(*) INTO v_cantidad FROM user_tab_columns
    WHERE table_name = 'AUDITORIA_TARIFA' AND column_name = 'USUARIO_ORACLE'
      AND data_type = 'VARCHAR2' AND nullable = 'N' AND char_length IN (30, 128);
    IF v_cantidad <> 1 THEN
        RAISE_APPLICATION_ERROR(-20406,
            'USUARIO_ORACLE debe ser VARCHAR2(30) o VARCHAR2(128) NOT NULL.');
    END IF;
    SELECT char_length INTO v_longitud_usuario FROM user_tab_columns
    WHERE table_name = 'AUDITORIA_TARIFA' AND column_name = 'USUARIO_ORACLE';
    IF existe_columna('AUDITORIA_TARIFA', 'ID_SENTENCIA') THEN
        exigir_columna('AUDITORIA_TARIFA', 'ID_SENTENCIA', 'RAW', 'Y', p_longitud => 16);
        exigir_sin_default('AUDITORIA_TARIFA', 'ID_SENTENCIA');
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_tab_columns
    WHERE table_name = 'AUDITORIA_TARIFA' AND column_name NOT IN (
        'ID_AUDITORIA', 'ID_TARIFA', 'USUARIO_ORACLE', 'FECHA_CAMBIO',
        'PRECIO_ANTERIOR', 'PRECIO_NUEVO', 'OPERACION', 'ID_SENTENCIA');
    IF v_cantidad <> 0 THEN
        RAISE_APPLICATION_ERROR(-20407, 'AUDITORIA_TARIFA contiene columnas fuera del contrato.');
    END IF;
    exigir_restriccion('AUDITORIA_TARIFA', 'PK_AUDITORIA_TARIFA', 'P');
    exigir_columnas_llave('PK_AUDITORIA_TARIFA', 'ID_AUDITORIA');
    exigir_restriccion('AUDITORIA_TARIFA', 'FK_AUDITORIA_TARIFA', 'R');
    exigir_columnas_llave('FK_AUDITORIA_TARIFA', 'ID_TARIFA');
    exigir_destino_fk('FK_AUDITORIA_TARIFA', 'TARIFA', 'ID_TARIFA');
    exigir_restriccion('AUDITORIA_TARIFA', 'CK_AUDITORIA_PRECIOS', 'C',
        'precio_anterior > 0 AND precio_nuevo > 0');
    exigir_restriccion('AUDITORIA_TARIFA', 'CK_AUDITORIA_OPERACION', 'C',
        q'~operacion IN ('UPDATE', 'DELETE')~');

    exigir_columna('LIQUIDACION_MENSUAL', 'ID_LIQUIDACION', 'NUMBER', 'N');
    exigir_columna('LIQUIDACION_MENSUAL', 'ID_ALOJAMIENTO', 'NUMBER', 'N');
    exigir_columna('LIQUIDACION_MENSUAL', 'PERIODO_ANIO', 'NUMBER', 'N', 4, 0);
    exigir_columna('LIQUIDACION_MENSUAL', 'PERIODO_MES', 'NUMBER', 'N', 2, 0);
    exigir_columna('LIQUIDACION_MENSUAL', 'TOTAL_HOSPEDAJE', 'NUMBER', 'N', 14, 2);
    exigir_columna('LIQUIDACION_MENSUAL', 'TOTAL_SERVICIOS', 'NUMBER', 'N', 14, 2);
    exigir_columna('LIQUIDACION_MENSUAL', 'COMISION_PLATAFORMA', 'NUMBER', 'N', 14, 2);
    exigir_columna('LIQUIDACION_MENSUAL', 'NETO_PROPIETARIO', 'NUMBER', 'N', 14, 2);
    exigir_columna('LIQUIDACION_MENSUAL', 'FECHA_LIQUIDACION', 'DATE', 'N');
    exigir_columna('LIQUIDACION_MENSUAL', 'ESTADO', 'VARCHAR2', 'N', p_longitud => 10);
    IF existe_columna('LIQUIDACION_MENSUAL', 'PORCENTAJE_COMISION') THEN
        exigir_columna('LIQUIDACION_MENSUAL', 'PORCENTAJE_COMISION', 'NUMBER', 'Y', 7, 4);
        exigir_sin_default('LIQUIDACION_MENSUAL', 'PORCENTAJE_COMISION');
        v_metadatos_presentes := v_metadatos_presentes + 1;
        v_predicado_parcial := 'porcentaje_comision IS NOT NULL';
    END IF;
    IF existe_columna('LIQUIDACION_MENSUAL', 'BASE_COMISION') THEN
        exigir_columna('LIQUIDACION_MENSUAL', 'BASE_COMISION', 'NUMBER', 'Y', 14, 2);
        exigir_sin_default('LIQUIDACION_MENSUAL', 'BASE_COMISION');
        v_metadatos_presentes := v_metadatos_presentes + 1;
        IF v_predicado_parcial IS NOT NULL THEN
            v_predicado_parcial := v_predicado_parcial || ' OR ';
        END IF;
        v_predicado_parcial := v_predicado_parcial || 'base_comision IS NOT NULL';
    END IF;
    IF existe_columna('LIQUIDACION_MENSUAL', 'CRITERIO_LIQUIDACION') THEN
        exigir_columna('LIQUIDACION_MENSUAL', 'CRITERIO_LIQUIDACION', 'VARCHAR2', 'Y',
                       p_longitud => 40);
        exigir_sin_default('LIQUIDACION_MENSUAL', 'CRITERIO_LIQUIDACION');
        v_metadatos_presentes := v_metadatos_presentes + 1;
        IF v_predicado_parcial IS NOT NULL THEN
            v_predicado_parcial := v_predicado_parcial || ' OR ';
        END IF;
        v_predicado_parcial := v_predicado_parcial || 'criterio_liquidacion IS NOT NULL';
    END IF;
    SELECT COUNT(*) INTO v_cantidad FROM user_tab_columns
    WHERE table_name = 'LIQUIDACION_MENSUAL' AND column_name NOT IN (
        'ID_LIQUIDACION', 'ID_ALOJAMIENTO', 'PERIODO_ANIO', 'PERIODO_MES',
        'TOTAL_HOSPEDAJE', 'TOTAL_SERVICIOS', 'COMISION_PLATAFORMA',
        'NETO_PROPIETARIO', 'FECHA_LIQUIDACION', 'ESTADO',
        'PORCENTAJE_COMISION', 'BASE_COMISION', 'CRITERIO_LIQUIDACION');
    IF v_cantidad <> 0 THEN
        RAISE_APPLICATION_ERROR(-20408, 'LIQUIDACION_MENSUAL contiene columnas fuera del contrato.');
    END IF;
    exigir_restriccion('LIQUIDACION_MENSUAL', 'PK_LIQUIDACION_MENSUAL', 'P');
    exigir_columnas_llave('PK_LIQUIDACION_MENSUAL', 'ID_LIQUIDACION');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'UQ_LIQUIDACION_PERIODO', 'U');
    exigir_columnas_llave('UQ_LIQUIDACION_PERIODO', 'ID_ALOJAMIENTO,PERIODO_ANIO,PERIODO_MES');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'FK_LIQUIDACION_ALOJAMIENTO', 'R');
    exigir_columnas_llave('FK_LIQUIDACION_ALOJAMIENTO', 'ID_ALOJAMIENTO');
    exigir_destino_fk('FK_LIQUIDACION_ALOJAMIENTO', 'ALOJAMIENTO', 'ID_ALOJAMIENTO');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'CK_LIQUIDACION_ANIO', 'C',
        'periodo_anio BETWEEN 2000 AND 9999');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'CK_LIQUIDACION_MES', 'C',
        'periodo_mes BETWEEN 1 AND 12');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'CK_LIQUIDACION_MONTOS', 'C',
        'total_hospedaje >= 0 AND total_servicios >= 0
         AND comision_plataforma >= 0 AND neto_propietario >= 0');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'CK_LIQUIDACION_CALCULO', 'C',
        'neto_propietario = ROUND(total_hospedaje + total_servicios - comision_plataforma, 2)');
    exigir_restriccion('LIQUIDACION_MENSUAL', 'CK_LIQUIDACION_ESTADO', 'C',
        q'~estado IN ('CALCULADA', 'DISPERSADA', 'PAGADA')~');
    revisar_check_existente('CK_LIQUIDACION_PORCENTAJE', c_regla_porcentaje);
    revisar_check_existente('CK_LIQUIDACION_METADATOS', c_regla_metadatos);
    revisar_check_existente('CK_LIQUIDACION_BASE_COMISION', c_regla_base);
    revisar_check_existente('CK_LIQUIDACION_COMISION_TASA', c_regla_comision);

    -- Una instalacion interrumpida puede tener columnas sin sus CHECK.
    -- Detectar datos incompatibles ANTES de modificar la estructura.
    IF v_metadatos_presentes = 3 THEN
        EXECUTE IMMEDIATE
            'SELECT COUNT(*) FROM liquidacion_mensual WHERE NOT ('
            || c_regla_metadatos || ') OR NOT (' || c_regla_porcentaje
            || ') OR NOT (' || c_regla_base || ') OR NOT (' || c_regla_comision || ')'
            INTO v_cantidad;
        IF v_cantidad <> 0 THEN
            RAISE_APPLICATION_ERROR(-20409,
                'Metadatos de liquidacion incompatibles. Reconciliar sin inferir antes de migrar.');
        END IF;
    ELSIF v_metadatos_presentes > 0 THEN
        EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM liquidacion_mensual WHERE '
            || v_predicado_parcial INTO v_cantidad;
        IF v_cantidad <> 0 THEN
            RAISE_APPLICATION_ERROR(-20410,
                'Hay metadatos parciales informados: no se completan por inferencia.');
        END IF;
    END IF;

    IF v_longitud_usuario = 30 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE auditoria_tarifa MODIFY (usuario_oracle VARCHAR2(128))';
        DBMS_OUTPUT.PUT_LINE('USUARIO_ORACLE ampliado a 128; eventos previos conservados.');
    END IF;
    IF NOT existe_columna('AUDITORIA_TARIFA', 'ID_SENTENCIA') THEN
        EXECUTE IMMEDIATE 'ALTER TABLE auditoria_tarifa ADD (id_sentencia RAW(16))';
        DBMS_OUTPUT.PUT_LINE('ID_SENTENCIA agregado sin default; legado permanece NULL.');
    END IF;
    IF NOT existe_columna('LIQUIDACION_MENSUAL', 'PORCENTAJE_COMISION') THEN
        EXECUTE IMMEDIATE 'ALTER TABLE liquidacion_mensual ADD (porcentaje_comision NUMBER(7,4))';
    END IF;
    IF NOT existe_columna('LIQUIDACION_MENSUAL', 'BASE_COMISION') THEN
        EXECUTE IMMEDIATE 'ALTER TABLE liquidacion_mensual ADD (base_comision NUMBER(14,2))';
    END IF;
    IF NOT existe_columna('LIQUIDACION_MENSUAL', 'CRITERIO_LIQUIDACION') THEN
        EXECUTE IMMEDIATE 'ALTER TABLE liquidacion_mensual ADD (criterio_liquidacion VARCHAR2(40))';
    END IF;
    crear_check_si_falta('CK_LIQUIDACION_PORCENTAJE', c_regla_porcentaje);
    crear_check_si_falta('CK_LIQUIDACION_METADATOS', c_regla_metadatos);
    crear_check_si_falta('CK_LIQUIDACION_BASE_COMISION', c_regla_base);
    crear_check_si_falta('CK_LIQUIDACION_COMISION_TASA', c_regla_comision);

    exigir_columna('AUDITORIA_TARIFA', 'USUARIO_ORACLE', 'VARCHAR2', 'N', p_longitud => 128);
    exigir_columna('AUDITORIA_TARIFA', 'ID_SENTENCIA', 'RAW', 'Y', p_longitud => 16);
    exigir_sin_default('AUDITORIA_TARIFA', 'ID_SENTENCIA');
    exigir_columna('LIQUIDACION_MENSUAL', 'PORCENTAJE_COMISION', 'NUMBER', 'Y', 7, 4);
    exigir_columna('LIQUIDACION_MENSUAL', 'BASE_COMISION', 'NUMBER', 'Y', 14, 2);
    exigir_columna('LIQUIDACION_MENSUAL', 'CRITERIO_LIQUIDACION', 'VARCHAR2', 'Y', p_longitud => 40);
    exigir_sin_default('LIQUIDACION_MENSUAL', 'PORCENTAJE_COMISION');
    exigir_sin_default('LIQUIDACION_MENSUAL', 'BASE_COMISION');
    exigir_sin_default('LIQUIDACION_MENSUAL', 'CRITERIO_LIQUIDACION');

    EXECUTE IMMEDIATE q'~COMMENT ON COLUMN auditoria_tarifa.id_sentencia IS
        'Identificador comun de sentencia nueva; NULL conserva agrupacion legada desconocida.'~';
    EXECUTE IMMEDIATE q'~COMMENT ON COLUMN auditoria_tarifa.fecha_cambio IS
        'Eventos nuevos del trigger: UTC. Los timestamps legados conservan su zona desconocida.'~';
    EXECUTE IMMEDIATE q'~COMMENT ON COLUMN liquidacion_mensual.porcentaje_comision IS
        'Porcentaje 0..100; NULL junto con base y criterio conserva politica legada desconocida.'~';
    EXECUTE IMMEDIATE q'~COMMENT ON COLUMN liquidacion_mensual.base_comision IS
        'Importe contratado de hospedaje mas servicios; no usa pagos ni TARIFA vigente.'~';
    EXECUTE IMMEDIATE q'~COMMENT ON COLUMN liquidacion_mensual.criterio_liquidacion IS
        'Politica aplicada: FINALIZADA_CHECKOUT_HMAS_SERV_V1 en Entrega 2. Legado NULL no se infiere.'~';

    DBMS_OUTPUT.PUT_LINE('Soporte estructural E2 verificado; datos legados sin inferencias.');
END;
/
