-- Actualizacion estructural del modelo de 21 a 22 tablas.
-- Ejecutar como propietario del proyecto, con respaldo previo.
-- Crea exclusivamente la tabla de tramos y su indice si no existen.
-- Si ya existen, verifica su contrato y falla ante incompatibilidades.
-- No rellena datos ni reconstruye precios usando el catalogo TARIFA actual.
-- Un historico sin tramos acreditados debe seguir pendiente de validacion.
-- El DDL de Oracle confirma cambios; ROLLBACK no revierte su instalacion.
SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE

DECLARE
    v_total PLS_INTEGER;

    PROCEDURE exigir_columna(
        p_nombre VARCHAR2,
        p_tipo VARCHAR2,
        p_nullable VARCHAR2,
        p_precision NUMBER DEFAULT NULL,
        p_escala NUMBER DEFAULT NULL,
        p_longitud NUMBER DEFAULT NULL
    ) IS
        v_coincidencias PLS_INTEGER;
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias
        FROM user_tab_columns
        WHERE table_name = 'RESERVA_HABITACION_TARIFA_APLICADA'
          AND column_name = p_nombre
          AND data_type = p_tipo
          AND nullable = p_nullable
          AND (data_precision = p_precision
               OR (data_precision IS NULL AND p_precision IS NULL))
          AND (data_scale = p_escala
               OR (data_scale IS NULL AND p_escala IS NULL))
          AND (p_longitud IS NULL OR char_length = p_longitud);
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20021,
                'Columna ausente o incompatible: ' || p_nombre);
        END IF;
    END;

    PROCEDURE exigir_restriccion(
        p_nombre VARCHAR2,
        p_tipo VARCHAR2,
        p_condicion VARCHAR2 DEFAULT NULL
    ) IS
        v_coincidencias PLS_INTEGER;
        v_condicion VARCHAR2(4000);
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias
        FROM user_constraints
        WHERE table_name = 'RESERVA_HABITACION_TARIFA_APLICADA'
          AND constraint_name = p_nombre
          AND constraint_type = p_tipo
          AND status = 'ENABLED'
          AND validated = 'VALIDATED';
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20022,
                'Restriccion ausente, incompatible o sin validar: ' || p_nombre);
        END IF;

        IF p_condicion IS NOT NULL THEN
            SELECT search_condition_vc INTO v_condicion
            FROM user_constraints
            WHERE constraint_name = p_nombre;
            IF REGEXP_REPLACE(UPPER(v_condicion), '[[:space:]"]', '')
               <> REGEXP_REPLACE(UPPER(p_condicion), '[[:space:]"]', '') THEN
                RAISE_APPLICATION_ERROR(-20023,
                    'Condicion incompatible en ' || p_nombre);
            END IF;
        END IF;
    END;

    PROCEDURE exigir_columnas_restriccion(
        p_nombre VARCHAR2,
        p_columnas VARCHAR2
    ) IS
        v_columnas VARCHAR2(4000);
    BEGIN
        SELECT LISTAGG(column_name, ',') WITHIN GROUP (ORDER BY position)
        INTO v_columnas
        FROM user_cons_columns
        WHERE table_name = 'RESERVA_HABITACION_TARIFA_APLICADA'
          AND constraint_name = p_nombre;
        IF v_columnas IS NULL OR v_columnas <> p_columnas THEN
            RAISE_APPLICATION_ERROR(-20024,
                'Columnas incompatibles en ' || p_nombre);
        END IF;
    END;

    PROCEDURE exigir_referencia(
        p_nombre VARCHAR2,
        p_tabla_destino VARCHAR2,
        p_columnas_destino VARCHAR2,
        p_regla_borrado VARCHAR2
    ) IS
        v_coincidencias PLS_INTEGER;
        v_columnas VARCHAR2(4000);
    BEGIN
        SELECT COUNT(*) INTO v_coincidencias
        FROM user_constraints hija
        JOIN user_constraints padre
          ON padre.constraint_name = hija.r_constraint_name
        WHERE hija.constraint_name = p_nombre
          AND hija.r_owner = SYS_CONTEXT('USERENV', 'SESSION_USER')
          AND hija.delete_rule = p_regla_borrado
          AND padre.table_name = p_tabla_destino
          AND padre.constraint_type IN ('P', 'U')
          AND padre.status = 'ENABLED'
          AND padre.validated = 'VALIDATED';
        IF v_coincidencias <> 1 THEN
            RAISE_APPLICATION_ERROR(-20025,
                'Destino de clave foranea incompatible: ' || p_nombre);
        END IF;

        SELECT LISTAGG(columna.column_name, ',')
               WITHIN GROUP (ORDER BY columna.position)
        INTO v_columnas
        FROM user_cons_columns columna
        JOIN user_constraints hija
          ON hija.r_constraint_name = columna.constraint_name
        WHERE hija.constraint_name = p_nombre;
        IF v_columnas IS NULL OR v_columnas <> p_columnas_destino THEN
            RAISE_APPLICATION_ERROR(-20026,
                'Columnas de destino incompatibles: ' || p_nombre);
        END IF;
    END;
BEGIN
    IF SYS_CONTEXT('USERENV', 'SESSION_USER') IN ('SYS', 'SYSTEM') THEN
        RAISE_APPLICATION_ERROR(-20020,
            'Ejecute la migracion con el propietario del proyecto.');
    END IF;

    SELECT COUNT(*) INTO v_total
    FROM user_tables
    WHERE table_name IN ('RESERVA_HABITACION', 'TEMPORADA');
    IF v_total <> 2 THEN
        RAISE_APPLICATION_ERROR(-20027,
            'Se requiere el modelo existente con RESERVA_HABITACION y TEMPORADA.');
    END IF;

    SELECT COUNT(*) INTO v_total
    FROM user_tables
    WHERE table_name = 'RESERVA_HABITACION_TARIFA_APLICADA';
    IF v_total = 0 THEN
        EXECUTE IMMEDIATE q'~
CREATE TABLE reserva_habitacion_tarifa_aplicada (
    id_reserva               NUMBER        NOT NULL,
    id_habitacion            NUMBER        NOT NULL,
    fecha_inicio_tramo       DATE          NOT NULL,
    fecha_fin_tramo          DATE          NOT NULL,
    id_temporada             NUMBER        NOT NULL,
    tipo_temporada_aplicado  VARCHAR2(5)   NOT NULL,
    precio_noche_aplicado    NUMBER(12,2)  NOT NULL,
    origen_dato              VARCHAR2(24)  NOT NULL,
    referencia_evidencia     VARCHAR2(200),
    CONSTRAINT pk_reserva_habitacion_tarifa_aplicada
        PRIMARY KEY (id_reserva, id_habitacion, fecha_inicio_tramo),
    CONSTRAINT ck_reserva_tarifa_tramo_fechas
        CHECK (fecha_fin_tramo > fecha_inicio_tramo),
    CONSTRAINT ck_reserva_tarifa_fechas_dia
        CHECK (fecha_inicio_tramo = TRUNC(fecha_inicio_tramo)
               AND fecha_fin_tramo = TRUNC(fecha_fin_tramo)),
    CONSTRAINT ck_reserva_tarifa_tipo
        CHECK (tipo_temporada_aplicado IN ('ALTA', 'MEDIA', 'BAJA')),
    CONSTRAINT ck_reserva_tarifa_precio
        CHECK (precio_noche_aplicado > 0),
    CONSTRAINT ck_reserva_tarifa_origen
        CHECK (origen_dato IN ('CAPTURADO', 'RECONSTRUIDO_VALIDADO')),
    CONSTRAINT ck_reserva_tarifa_evidencia
        CHECK (origen_dato = 'CAPTURADO'
               OR (origen_dato = 'RECONSTRUIDO_VALIDADO'
                   AND TRIM(referencia_evidencia) IS NOT NULL)),
    CONSTRAINT fk_reserva_tarifa_habitacion
        FOREIGN KEY (id_reserva, id_habitacion)
        REFERENCES reserva_habitacion (id_reserva, id_habitacion)
        ON DELETE CASCADE,
    CONSTRAINT fk_reserva_tarifa_temporada
        FOREIGN KEY (id_temporada)
        REFERENCES temporada (id_temporada)
)~';
        DBMS_OUTPUT.PUT_LINE('Tabla de tramos creada; no se insertaron datos.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Tabla existente: se verifica sin modificar datos.');
    END IF;

    SELECT COUNT(*) INTO v_total
    FROM user_tab_columns
    WHERE table_name = 'RESERVA_HABITACION_TARIFA_APLICADA';
    IF v_total <> 9 THEN
        RAISE_APPLICATION_ERROR(-20028,
            'La tabla existente no tiene las nueve columnas del contrato.');
    END IF;
    exigir_columna('ID_RESERVA', 'NUMBER', 'N');
    exigir_columna('ID_HABITACION', 'NUMBER', 'N');
    exigir_columna('FECHA_INICIO_TRAMO', 'DATE', 'N');
    exigir_columna('FECHA_FIN_TRAMO', 'DATE', 'N');
    exigir_columna('ID_TEMPORADA', 'NUMBER', 'N');
    exigir_columna('TIPO_TEMPORADA_APLICADO', 'VARCHAR2', 'N',
                   p_longitud => 5);
    exigir_columna('PRECIO_NOCHE_APLICADO', 'NUMBER', 'N', 12, 2);
    exigir_columna('ORIGEN_DATO', 'VARCHAR2', 'N', p_longitud => 24);
    exigir_columna('REFERENCIA_EVIDENCIA', 'VARCHAR2', 'Y', p_longitud => 200);

    exigir_restriccion('PK_RESERVA_HABITACION_TARIFA_APLICADA', 'P');
    exigir_columnas_restriccion('PK_RESERVA_HABITACION_TARIFA_APLICADA',
        'ID_RESERVA,ID_HABITACION,FECHA_INICIO_TRAMO');
    exigir_restriccion('FK_RESERVA_TARIFA_HABITACION', 'R');
    exigir_columnas_restriccion('FK_RESERVA_TARIFA_HABITACION',
        'ID_RESERVA,ID_HABITACION');
    exigir_referencia('FK_RESERVA_TARIFA_HABITACION', 'RESERVA_HABITACION',
        'ID_RESERVA,ID_HABITACION', 'CASCADE');
    exigir_restriccion('FK_RESERVA_TARIFA_TEMPORADA', 'R');
    exigir_columnas_restriccion('FK_RESERVA_TARIFA_TEMPORADA', 'ID_TEMPORADA');
    exigir_referencia('FK_RESERVA_TARIFA_TEMPORADA', 'TEMPORADA',
        'ID_TEMPORADA', 'NO ACTION');
    exigir_restriccion('CK_RESERVA_TARIFA_TRAMO_FECHAS', 'C',
        'fecha_fin_tramo > fecha_inicio_tramo');
    exigir_restriccion('CK_RESERVA_TARIFA_FECHAS_DIA', 'C',
        'fecha_inicio_tramo = TRUNC(fecha_inicio_tramo)
         AND fecha_fin_tramo = TRUNC(fecha_fin_tramo)');
    exigir_restriccion('CK_RESERVA_TARIFA_TIPO', 'C',
        q'~tipo_temporada_aplicado IN ('ALTA', 'MEDIA', 'BAJA')~');
    exigir_restriccion('CK_RESERVA_TARIFA_PRECIO', 'C',
        'precio_noche_aplicado > 0');
    exigir_restriccion('CK_RESERVA_TARIFA_ORIGEN', 'C',
        q'~origen_dato IN ('CAPTURADO', 'RECONSTRUIDO_VALIDADO')~');
    exigir_restriccion('CK_RESERVA_TARIFA_EVIDENCIA', 'C',
        q'~origen_dato = 'CAPTURADO'
           OR (origen_dato = 'RECONSTRUIDO_VALIDADO'
               AND TRIM(referencia_evidencia) IS NOT NULL)~');

    SELECT COUNT(*) INTO v_total
    FROM user_indexes
    WHERE index_name = 'IX_RESERVA_TARIFA_TEMPORADA';
    IF v_total = 0 THEN
        EXECUTE IMMEDIATE
            'CREATE INDEX ix_reserva_tarifa_temporada'
            || ' ON reserva_habitacion_tarifa_aplicada (id_temporada)';
        DBMS_OUTPUT.PUT_LINE('Indice de temporada creado.');
    ELSE
        SELECT COUNT(*) INTO v_total
        FROM user_indexes
        WHERE index_name = 'IX_RESERVA_TARIFA_TEMPORADA'
          AND table_name = 'RESERVA_HABITACION_TARIFA_APLICADA'
          AND index_type = 'NORMAL'
          AND uniqueness = 'NONUNIQUE'
          AND status = 'VALID';
        IF v_total <> 1 THEN
            RAISE_APPLICATION_ERROR(-20029,
                'IX_RESERVA_TARIFA_TEMPORADA existe con una definicion incompatible.');
        END IF;

        SELECT COUNT(*) INTO v_total
        FROM user_ind_columns
        WHERE index_name = 'IX_RESERVA_TARIFA_TEMPORADA';
        IF v_total <> 1 THEN
            RAISE_APPLICATION_ERROR(-20030,
                'El indice de temporada contiene columnas inesperadas.');
        END IF;
        SELECT COUNT(*) INTO v_total
        FROM user_ind_columns
        WHERE index_name = 'IX_RESERVA_TARIFA_TEMPORADA'
          AND column_name = 'ID_TEMPORADA'
          AND column_position = 1
          AND descend = 'ASC';
        IF v_total <> 1 THEN
            RAISE_APPLICATION_ERROR(-20031,
                'El indice de temporada no cubre ID_TEMPORADA ascendente.');
        END IF;
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Estructura verificada. Ejecute la validacion de conjuntos antes de analitica.');
END;
/
