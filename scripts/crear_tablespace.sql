-- Infraestructura de TurismoUQ; ejecutar como administrador en XEPDB1.
-- Los dos argumentos son obligatorios y no deben contener comillas simples
-- ni el caracter ~. La ruta pertenece al servidor Oracle, no al cliente.
--
-- Perfil OMF: requiere DB_CREATE_FILE_DEST ya configurado en la sesion/PDB.
--   @scripts/crear_tablespace.sql OMF SIN_RUTA
-- Perfil RUTA: archivo absoluto del servidor, tambien si contiene espacios.
--   @scripts/crear_tablespace.sql RUTA "C:\app\oradata\XEPDB1\historico.dbf"
--   @scripts/crear_tablespace.sql RUTA /opt/oracle/oradata/XEPDB1/historico.dbf
--
-- No cambia DB_CREATE_FILE_DEST, no reutiliza ni borra archivos y no modifica
-- un tablespace existente. Las cuotas se conceden aparte al usuario proyecto.
SET ECHO OFF
SET VERIFY OFF
SET DEFINE ON
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE

DECLARE
    v_perfil       VARCHAR2(20) := UPPER(TRIM('&1'));
    v_ruta         VARCHAR2(4000) := TRIM(BOTH '"' FROM TRIM(q'~&2~'));
    v_destino_omf  VARCHAR2(4000);
    v_existentes   PLS_INTEGER;
    v_contenido    VARCHAR2(20);
    v_estado       VARCHAR2(20);
    v_sentencia    VARCHAR2(5000);
BEGIN
    IF SYS_CONTEXT('USERENV', 'CON_NAME') <> 'XEPDB1' THEN
        RAISE_APPLICATION_ERROR(-20010,
            'Conectese a XEPDB1 antes de crear el tablespace del proyecto.');
    END IF;

    IF v_perfil IS NULL OR v_perfil NOT IN ('OMF', 'RUTA') THEN
        RAISE_APPLICATION_ERROR(-20011, 'Perfil requerido: OMF o RUTA.');
    END IF;

    SELECT COUNT(*) INTO v_existentes
    FROM dba_tablespaces
    WHERE tablespace_name = 'TS_HISTORICO_RESERVAS';

    IF v_existentes = 1 THEN
        SELECT contents, status INTO v_contenido, v_estado
        FROM dba_tablespaces
        WHERE tablespace_name = 'TS_HISTORICO_RESERVAS';
        IF v_contenido <> 'PERMANENT' OR v_estado <> 'ONLINE' THEN
            RAISE_APPLICATION_ERROR(-20012,
                'El tablespace existente no es permanente y online. Reviselo.');
        END IF;
        DBMS_OUTPUT.PUT_LINE(
            'TS_HISTORICO_RESERVAS ya existe: se conserva sin modificaciones.');
        RETURN;
    END IF;

    IF v_perfil = 'OMF' THEN
        SELECT value INTO v_destino_omf
        FROM v$parameter
        WHERE name = 'db_create_file_dest';

        IF TRIM(v_destino_omf) IS NULL THEN
            RAISE_APPLICATION_ERROR(-20013,
                'OMF no esta configurado. Use RUTA con archivo absoluto.');
        END IF;
        v_sentencia := 'CREATE TABLESPACE ts_historico_reservas DATAFILE';
    ELSE
        IF v_ruta IS NULL OR NOT (
            SUBSTR(v_ruta, 1, 1) = '/'
            OR REGEXP_LIKE(v_ruta, '^[A-Za-z]:[\\/]')
            OR SUBSTR(v_ruta, 1, 2) = '\\'
        ) THEN
            RAISE_APPLICATION_ERROR(-20014,
                'RUTA requiere el nombre absoluto de un archivo del servidor.');
        END IF;
        v_sentencia := 'CREATE TABLESPACE ts_historico_reservas DATAFILE '
            || DBMS_ASSERT.ENQUOTE_LITERAL(v_ruta);
    END IF;

    v_sentencia := v_sentencia
        || ' SIZE 100M AUTOEXTEND ON NEXT 25M MAXSIZE 1G'
        || ' EXTENT MANAGEMENT LOCAL AUTOALLOCATE'
        || ' SEGMENT SPACE MANAGEMENT AUTO';
    EXECUTE IMMEDIATE v_sentencia;
    DBMS_OUTPUT.PUT_LINE('TS_HISTORICO_RESERVAS creado con perfil ' || v_perfil);
END;
/

UNDEFINE 1
UNDEFINE 2
SET DEFINE OFF
