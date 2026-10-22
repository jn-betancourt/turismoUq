-- Validacion de binds de la consulta 5; no declara ni asigna sus valores.
-- En GUI, ejecutar este bloque con los mismos binds que el SELECT canonico.
-- No modifica datos ni confirma transacciones.
-- Fija el calendario de esta sesion para interpretar fechas gregorianas.
DECLARE
    v_fecha_inicio DATE;
    v_fecha_fin DATE;
BEGIN
    EXECUTE IMMEDIATE q'[ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN']';
    IF :fecha_ini IS NULL OR :fecha_fin IS NULL THEN
        RAISE_APPLICATION_ERROR(-20051,
            'Consulta 5: fecha_ini y fecha_fin son obligatorias (YYYY-MM-DD).');
    END IF;

    IF NOT REGEXP_LIKE(:fecha_ini, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
       OR NOT REGEXP_LIKE(:fecha_fin, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$') THEN
        RAISE_APPLICATION_ERROR(-20052,
            'Consulta 5: ambas fechas deben tener formato exacto YYYY-MM-DD.');
    END IF;

    BEGIN
        v_fecha_inicio := TO_DATE(:fecha_ini, 'FXYYYY-MM-DD');
        v_fecha_fin := TO_DATE(:fecha_fin, 'FXYYYY-MM-DD');
    EXCEPTION
        WHEN OTHERS THEN
            RAISE_APPLICATION_ERROR(-20052,
                'Consulta 5: alguna fecha no existe o no respeta YYYY-MM-DD.');
    END;

    IF v_fecha_inicio > v_fecha_fin THEN
        RAISE_APPLICATION_ERROR(-20053,
            'Consulta 5: fecha_ini debe ser anterior o igual a fecha_fin.');
    END IF;

    IF v_fecha_fin = DATE '9999-12-31' THEN
        RAISE_APPLICATION_ERROR(-20054,
            'Consulta 5: fecha_fin debe permitir calcular el dia siguiente.');
    END IF;
END;
/
