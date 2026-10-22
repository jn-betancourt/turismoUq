"""Verifica la Entrega 1 en Oracle local sin modificar el esquema original.

Crea tres esquemas NUEVOS; nunca borra ni restablece cuentas existentes.
Las claves se generan en memoria y SQL*Plus las recibe por entrada estandar.
El propietario puede elegir despues su clave con PASSWORD <esquema>.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPENDENCIES = ROOT / '.validation-deps'
if LOCAL_DEPENDENCIES.is_dir():
    sys.path.insert(0, str(LOCAL_DEPENDENCIES))


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema-prefix', default='TURISMOUQ_E1')
    parser.add_argument('--service', default='localhost:1521/xepdb1')
    parser.add_argument('--pdb', default='XEPDB1')
    parser.add_argument('--sqlplus', default=shutil.which('sqlplus') or 'sqlplus')
    oracle_home = os.environ.get('ORACLE_HOME')
    default_client = str(Path(oracle_home) / 'bin') if oracle_home else str(Path(parser.get_default('sqlplus')).resolve().parent)
    parser.add_argument('--oracle-client-lib', default=default_client)
    parser.add_argument('--preserve-schema', default='TURISMOUQ')
    return parser.parse_args()


def checked_identifier(value):
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', value):
        raise ValueError('Nombre Oracle requerido: mayusculas, numeros o _, maximo 30 caracteres.')
    return value


def json_value(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_value) + '\n', encoding='utf-8')


def executable_hashes():
    result = {}
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
            continue
        if path.is_file() and path.suffix in ('.sql', '.py'):
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def schema_fingerprint(connection, schema):
    cursor = connection.cursor()
    cursor.execute('''SELECT table_name FROM dba_tables WHERE owner = :owner
                      AND table_name NOT IN (SELECT mview_name FROM dba_mviews WHERE owner = :owner)
                      ORDER BY table_name''', owner=schema)
    tables = [row[0] for row in cursor]
    result = {}
    for table in tables:
        cursor.execute('''SELECT col.column_name FROM dba_constraints con
                          JOIN dba_cons_columns col ON col.owner=con.owner
                            AND col.constraint_name=con.constraint_name
                          WHERE con.owner=:owner AND con.table_name=:table_name
                            AND con.constraint_type='P' ORDER BY col.position''',
                       owner=schema, table_name=table)
        primary_key = [row[0] for row in cursor]
        if not primary_key:
            raise RuntimeError('No hay PK para ordenar la huella de ' + schema + '.' + table)
        order_clause = ','.join('"' + column + '"' for column in primary_key)
        cursor.execute(f'SELECT * FROM "{schema}"."{table}" ORDER BY {order_clause}')
        digest = hashlib.sha256()
        count = 0
        for row in cursor:
            digest.update(json.dumps(row, default=json_value, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8'))
            digest.update(b'\n')
            count += 1
        result[table] = {'rows': count, 'sha256': digest.hexdigest()}
    return result


class SqlPlusRunner:
    def __init__(self, executable, service, evidence, passwords, *, allow_compilation_warnings=False):
        self.executable = executable
        self.service = service
        self.evidence = evidence
        self.passwords = passwords
        self.allow_compilation_warnings = allow_compilation_warnings

    def execute(self, schema, content, label, *, expect_failure=False):
        arguments = [self.executable, '-L', '-S']
        if schema is None:
            arguments += ['/', 'as', 'sysdba']
            password_input = ''
        else:
            arguments += [schema + '@' + self.service]
            password_input = self.passwords[schema] + '\n'
        settings = '''SET ECHO OFF
SET VERIFY OFF
SET DEFINE OFF
SET SQLBLANKLINES ON
SET SERVEROUTPUT ON
SET PAGESIZE 200
SET LINESIZE 240
SET TRIMSPOOL ON
WHENEVER OSERROR EXIT FAILURE ROLLBACK
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
'''
        environment = dict(os.environ, NLS_LANG='AMERICAN_AMERICA.AL32UTF8')
        process = subprocess.run(arguments, input=password_input + settings + content + '\nEXIT ROLLBACK\n',
                                 text=True, encoding='utf-8', errors='replace', cwd=ROOT,
                                 env=environment, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=300)
        output = process.stdout
        for password in self.passwords.values():
            output = output.replace(password, '[REDACTED]')
        (self.evidence / (label + '.log')).write_text(output, encoding='utf-8')
        errors = re.findall(r'(?m)^\s*(?:ORA|SP2|PLS)-\d+[^\r\n]*', output)
        if self.allow_compilation_warnings:
            # SP2-0810 informa advertencias; USER_ERRORS/ATTRIBUTE=ERROR y
            # los estados VALID del instalador siguen siendo obligatorios.
            errors = [error for error in errors if not re.search(r'\bSP2-0810:', error)]
        failed = process.returncode != 0 or bool(errors)
        if failed and not expect_failure:
            raise RuntimeError(label + ': ' + '; '.join(errors or ['salida=' + str(process.returncode)]))
        if expect_failure and not failed:
            raise RuntimeError(label + ': se esperaba rechazo y la ejecucion fue aceptada.')
        return output

    def file(self, schema, path, label):
        return self.execute(schema, '@"' + str((ROOT / path).resolve()) + '"', label)


def plsql_blocks(path):
    text = path.read_text(encoding='utf-8')
    return [match.group(1).rstrip() for match in
            re.finditer(r'(?ms)^((?:DECLARE|BEGIN)\b.*?^END;)[ \t]*\r?\n/', text)]


def integrity_negative_tests(connection):
    blocks = plsql_blocks(ROOT / 'scripts/verificar_entrega1.sql')
    if len(blocks) != 2:
        raise RuntimeError('Se esperaban los dos bloques de verificacion de datos.')
    cursor = connection.cursor()

    def verify():
        for block in blocks:
            cursor.execute(block)

    observed = []
    mutations = [
        ('tarifa faltante', 'DELETE FROM tarifa WHERE id_tarifa=(SELECT MIN(id_tarifa) FROM tarifa)', 20116),
        ('capacidad excedida', '''UPDATE reserva_habitacion rh SET personas_hospedadas=999
             WHERE (id_reserva,id_habitacion)=(SELECT id_reserva,id_habitacion
                  FROM reserva_habitacion ORDER BY id_reserva,id_habitacion FETCH FIRST 1 ROW ONLY)''', 20108),
        ('temporadas solapadas', '''UPDATE temporada SET fecha_inicio=(SELECT fecha_fin FROM temporada WHERE id_temporada=1)
             WHERE id_temporada=2''', 20113),
    ]
    for label, statement, expected_code in mutations:
        cursor.execute('SAVEPOINT negative_case')
        try:
            cursor.execute(statement)
            try:
                verify()
            except Exception as error:
                error_code = getattr(error.args[0], 'code', None)
                if error_code != expected_code:
                    raise RuntimeError(f'{label}: se esperaba {expected_code}, obtenido {error_code}') from error
                observed.append({'anomaly': label, 'rejected_with': error_code})
            else:
                raise RuntimeError(label + ': el verificador no rechazo la anomalia.')
        finally:
            cursor.execute('ROLLBACK TO negative_case')
    results = [{'id': 'I01', 'status': 'PASS', 'expected': 'Rechazar las tres anomalias de cobertura/capacidad',
                'observed': observed}]
    cursor.execute('''SELECT COUNT(*) FROM reserva_habitacion a JOIN reserva ra ON ra.id_reserva=a.id_reserva
                      JOIN reserva_habitacion b ON b.id_habitacion=a.id_habitacion AND b.id_reserva>a.id_reserva
                      JOIN reserva rb ON rb.id_reserva=b.id_reserva
                      WHERE ra.fecha_checkout=rb.fecha_checkin OR rb.fecha_checkout=ra.fecha_checkin''')
    contiguous_pairs = cursor.fetchone()[0]
    if contiguous_pairs == 0:
        raise RuntimeError('El conjunto no permite comprobar reservas contiguas.')
    verify()
    cursor.execute('''SELECT a.id_reserva,b.id_reserva FROM reserva_habitacion a
                      JOIN reserva_habitacion b ON b.id_habitacion=a.id_habitacion AND b.id_reserva>a.id_reserva
                      JOIN reserva ra ON ra.id_reserva=a.id_reserva
                      JOIN reserva rb ON rb.id_reserva=b.id_reserva
                      WHERE ra.estado <> 'CANCELADA' AND rb.estado <> 'CANCELADA'
                      ORDER BY a.id_reserva,b.id_reserva FETCH FIRST 1 ROW ONLY''')
    first_reservation, second_reservation = cursor.fetchone()
    cursor.execute('SAVEPOINT overlapping_case')
    try:
        cursor.execute('''UPDATE reserva SET (fecha_checkin,fecha_checkout)=(
                          SELECT fecha_checkin,fecha_checkout FROM reserva WHERE id_reserva=:first_id)
                          WHERE id_reserva=:second_id''', first_id=first_reservation, second_id=second_reservation)
        try:
            verify()
        except Exception as error:
            error_code = getattr(error.args[0], 'code', None)
            if error_code != 20118:
                raise RuntimeError('El solapamiento no fue detectado con el criterio esperado.') from error
        else:
            raise RuntimeError('El verificador acepto el solapamiento.')
    finally:
        cursor.execute('ROLLBACK TO overlapping_case')
    results.append({'id': 'I02', 'status': 'PASS', 'expected': 'Aceptar contiguas y rechazar superpuestas',
                    'observed': {'contiguous_pairs_accepted': contiguous_pairs, 'overlap_error': 20118}})
    connection.rollback()
    return results


def main():
    arguments = parse_arguments()
    import oracledb
    prefix = checked_identifier(arguments.schema_prefix.upper())
    schemas = [prefix, checked_identifier(prefix + '_REPRO'), checked_identifier(prefix + '_TEST')]
    preserved = checked_identifier(arguments.preserve_schema.upper())
    if preserved in schemas:
        raise ValueError('El esquema que se conserva no puede ser un esquema de pruebas.')
    pdb = checked_identifier(arguments.pdb.upper())
    run_id = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).strftime('%Y-%m-%d_%H%M%S')
    evidence = ROOT / 'evidencias' / 'entrega1' / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    report = {'status': 'RUNNING', 'schemas': schemas, 'preserved_schema': preserved,
              'run_id': run_id, 'source_sha256': executable_hashes(), 'tests': []}
    started = time.monotonic()
    try:
        oracledb.init_oracle_client(lib_dir=arguments.oracle_client_lib)
        with oracledb.connect(externalauth=True, mode=oracledb.AUTH_MODE_SYSDBA) as admin:
            cursor = admin.cursor()
            cursor.execute('ALTER SESSION SET CONTAINER=' + pdb)
            cursor.execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
            cursor.execute('SELECT banner_full FROM v$version WHERE banner_full LIKE \'Oracle Database%\'')
            report['oracle'] = cursor.fetchone()[0]
            report['python_oracledb'] = oracledb.__version__
            report['python'] = sys.version
            report['operating_system'] = platform.platform()
            report['oracle_client'] = list(oracledb.clientversion())
            report['base_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            report['service'] = arguments.service
            report['seed'] = 20262
            report['reference_time'] = '2026-10-22T12:00:00-05:00'
            cursor.execute('SELECT username FROM dba_users WHERE username IN (:a,:b,:c)', schemas)
            existing = [row[0] for row in cursor]
            if existing:
                raise RuntimeError('Se conservan las cuentas existentes; elija otro prefijo: ' + ', '.join(existing))
            before = schema_fingerprint(admin, preserved)
            write_json(evidence / 'original_before.json', before)
            if not before:
                raise RuntimeError('No se encontro el esquema original que debe conservarse.')
            passwords = {schema: 'Uq' + secrets.token_hex(12) for schema in schemas}
            for schema in schemas:
                cursor.execute(f'CREATE USER "{schema}" IDENTIFIED BY "{passwords[schema]}" DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP QUOTA UNLIMITED ON USERS')
                cursor.execute(f'GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE MATERIALIZED VIEW, CREATE SEQUENCE TO "{schema}"')
                cursor.execute(f'ALTER USER "{schema}" QUOTA UNLIMITED ON TS_HISTORICO_RESERVAS')
            runner = SqlPlusRunner(arguments.sqlplus, arguments.service, evidence, passwords)
            for index, schema in enumerate(schemas):
                print('Preparando esquema aislado ' + schema, flush=True)
                runner.file(schema, '01_DDL_TURISMOUQ_ORACLE21C.sql', schema + '_ddl')
                if index < 2:
                    # The second seed starts with a different client calendar.
                    initial_calendar = 'GREGORIAN' if index == 0 else 'PERSIAN'
                    runner.execute(schema, "ALTER SESSION SET NLS_CALENDAR='" + initial_calendar
                                   + "';\n@02_carga.sql", schema + '_carga')
                else:
                    # This table was just created empty by this run, in a NEW test account.
                    runner.execute(schema, '''DECLARE
    v_rows NUMBER;
BEGIN
    IF SUBSTR(USER, -5) <> '_TEST' THEN
        RAISE_APPLICATION_ERROR(-20201, 'Solo se admite el esquema aislado de pruebas.');
    END IF;
    SELECT COUNT(*) INTO v_rows FROM reserva_habitacion_tarifa_aplicada;
    IF v_rows <> 0 THEN
        RAISE_APPLICATION_ERROR(-20202, 'No se elimina una tabla con datos.');
    END IF;
    EXECUTE IMMEDIATE 'DROP TABLE reserva_habitacion_tarifa_aplicada PURGE';
END;
/
''', 'preparar_legacy_vacio')
                    runner.file(schema, 'migraciones/001_tramos_tarifarios.sql', 'migracion_legacy_vacio')
                runner.file(schema, 'scripts/preparar_analitica.sql', schema + '_analitica')
            main_fingerprint = schema_fingerprint(admin, schemas[0])
            repro_fingerprint = schema_fingerprint(admin, schemas[1])
            write_json(evidence / 'data_main.json', main_fingerprint)
            write_json(evidence / 'data_repro.json', repro_fingerprint)
            if main_fingerprint != repro_fingerprint:
                differences = [name for name in main_fingerprint
                               if main_fingerprint[name] != repro_fingerprint.get(name)]
                raise RuntimeError('Carga no reproducible: ' + ', '.join(differences))
            report['reproducibility'] = {'status': 'PASS', 'tables': len(main_fingerprint),
                                         'all_rows_identical': True,
                                         'initial_client_calendars': ['GREGORIAN', 'PERSIAN']}
            output = runner.execute(schemas[0], '''ALTER SESSION SET NLS_CALENDAR='PERSIAN';
@03_consultas_analisis.sql
SET HEADING OFF
SET FEEDBACK OFF
SELECT 'CALENDAR=' || value FROM nls_session_parameters WHERE parameter='NLS_CALENDAR';
''', 'ocho_consultas_sqlplus')
            if 'CALENDAR=GREGORIAN' not in output:
                raise RuntimeError('El lanzador no fijo el calendario gregoriano de la sesion.')
            report['calendar_profile'] = {'status': 'PASS', 'initial': 'PERSIAN',
                                          'effective': 'GREGORIAN', 'queries_executed': 8}
            runner.file(schemas[0], 'migraciones/001_tramos_tarifarios.sql', 'migracion_idempotente')
            with oracledb.connect(user=schemas[0], password=passwords[schemas[0]], dsn=arguments.service) as owner:
                owner.cursor().execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
                report['tests'].extend(integrity_negative_tests(owner))
                query = (ROOT / 'consultas/05_consulta_parametrizada.sql').read_text(encoding='utf-8')
                query = '\n'.join(line for line in query.splitlines() if not line.lstrip().startswith('--')).strip().rstrip(';')
                query_cursor = owner.cursor()
                query_cursor.execute(query, fecha_ini='2025-06-01', fecha_fin='2025-07-31')
                driver_rows = [list(row) for row in query_cursor]
                output = runner.execute(schemas[0], '''VARIABLE fecha_ini VARCHAR2(10)
VARIABLE fecha_fin VARCHAR2(10)
EXEC :fecha_ini := '2025-06-01';
EXEC :fecha_fin := '2025-07-31';
SET FEEDBACK OFF
SET MARKUP CSV ON
PROMPT RESULT_BEGIN
@"''' + str(ROOT / 'consultas/05_consulta_parametrizada.sql') + '''"
PROMPT RESULT_END
''', 'parametros_segundo_cliente')
                result_text = output.split('RESULT_BEGIN', 1)[1].split('RESULT_END', 1)[0].strip()
                sqlplus_rows = list(csv.reader(io.StringIO(result_text)))
                expected_rows = [list(row[:2]) + [Decimal(str(value)) if value is not None else None for value in row[2:]]
                                 for row in driver_rows]
                actual_rows = [row[:2] + [Decimal(value) if value else None for value in row[2:]]
                               for row in sqlplus_rows[1:]]
                if actual_rows != expected_rows:
                    raise RuntimeError('La consulta parametrizada no coincide entre SQLPlus y python-oracledb.')
                report['tests'].append({'id': 'P04', 'status': 'PASS', 'expected': 'Resultados iguales con binds desde dos clientes',
                                        'observed': {'clients': ['SQLPlus', 'python-oracledb'], 'rows': len(driver_rows)}})
            module_path = ROOT / 'tests/probar_consultas.py'
            specification = importlib.util.spec_from_file_location('query_tests', module_path)
            module = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(module)
            with oracledb.connect(user=schemas[2], password=passwords[schemas[2]], dsn=arguments.service) as test_owner:
                test_owner.cursor().execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
                report['tests'].extend(module.run_query_tests(test_owner, ROOT, evidence))
            runner.file(schemas[0], 'scripts/verificar_entrega1.sql', 'verificacion_final')
            after = schema_fingerprint(admin, preserved)
            write_json(evidence / 'original_after.json', after)
            if before != after:
                raise RuntimeError('El esquema original cambio durante la verificacion.')
            report['original_preserved'] = {'status': 'PASS', 'tables': len(before), 'all_rows_identical': True}
            if report['source_sha256'] != executable_hashes():
                raise RuntimeError('Los scripts ejecutables cambiaron durante la corrida; se requiere repetir.')
            test_ids = [result['id'] for result in report['tests']]
            if len(test_ids) != 23 or len(set(test_ids)) != 23 or any(result['status'] != 'PASS' for result in report['tests']):
                raise RuntimeError('La matriz de 23 casos no termino completa y aprobada.')
            report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = str(error)
        raise
    finally:
        report['duration_seconds'] = round(time.monotonic() - started, 2)
        write_json(evidence / 'resultado.json', report)
        print('Evidencia: ' + str(evidence), flush=True)
    print('APROBADA: 23 casos, 8 consultas, dos cargas identicas y esquema original conservado.', flush=True)


if __name__ == '__main__':
    main()
