"""Instala y prueba E2 en cuentas propias, conservando TURISMOUQ y TURISMOUQ_E1.

Las claves son aleatorias y solo viven en memoria. --resume-owned-run permite
reintentar una corrida propia: comprueba las fechas de creacion de sus cuentas
y cambia SOLO esas claves de validacion; nunca las cuentas preservadas.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import time

from validar_local import (ROOT, SqlPlusRunner, checked_identifier,
                           integrity_negative_tests, schema_fingerprint, write_json)
from probar_consultas import MODEL_TABLES, run_query_tests

PRESERVED = ('TURISMOUQ', 'TURISMOUQ_E1')
BASE_E1_COMMIT = '06f5bd452ab22143ceb4f7a7760248ac5137f85d'


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema-prefix', default='TURISMOUQ_E2')
    parser.add_argument('--service', default='localhost:1521/xepdb1')
    parser.add_argument('--pdb', default='XEPDB1')
    parser.add_argument('--sqlplus', default=shutil.which('sqlplus') or 'sqlplus')
    home = os.environ.get('ORACLE_HOME')
    client = str(Path(home) / 'bin') if home else str(Path(parser.get_default('sqlplus')).resolve().parent)
    parser.add_argument('--oracle-client-lib', default=client)
    parser.add_argument('--resume-owned-run', type=Path,
                        help='Directorio de una corrida propia; verifica cuentas antes de rotar sus claves.')
    return parser.parse_args()


def source_hashes():
    result = {}
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part.startswith('.') or part in ('__pycache__', 'evidencias') for part in relative.parts):
            continue
        if path.is_file() and path.suffix in ('.sql', '.py', '.pks', '.pkb'):
            result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def compare_parameter_clients(owner, runner, schema):
    query = (ROOT / 'consultas/05_consulta_parametrizada.sql').read_text(encoding='utf-8')
    query = '\n'.join(line for line in query.splitlines() if not line.lstrip().startswith('--')).strip().rstrip(';')
    with owner.cursor() as cursor:
        cursor.execute(query, fecha_ini='2025-06-01', fecha_fin='2025-07-31')
        expected = [list(row[:2]) + [Decimal(str(value)) if value is not None else None for value in row[2:]]
                    for row in cursor]
    output = runner.execute(schema, '''ALTER SESSION SET NLS_CALENDAR='GREGORIAN';
VARIABLE fecha_ini VARCHAR2(10)
VARIABLE fecha_fin VARCHAR2(10)
EXEC :fecha_ini := '2025-06-01';
EXEC :fecha_fin := '2025-07-31';
SET FEEDBACK OFF
SET MARKUP CSV ON
PROMPT RESULT_BEGIN
@consultas/05_consulta_parametrizada.sql
PROMPT RESULT_END
''', 'parametros_dos_clientes')
    content = output.split('RESULT_BEGIN', 1)[1].split('RESULT_END', 1)[0].strip()
    rows = list(csv.reader(io.StringIO(content)))
    actual = [row[:2] + [Decimal(value) if value else None for value in row[2:]] for row in rows[1:]]
    if actual != expected:
        raise AssertionError('Consulta 5 diferente entre SQLPlus y python-oracledb.')
    return {'id': 'P04', 'status': 'PASS', 'expected': 'Mismos binds y filas desde dos clientes',
            'observed': {'clients': ['SQLPlus', 'python-oracledb'], 'rows': len(actual)}}


def main():
    options = arguments()
    import oracledb
    prefix = checked_identifier(options.schema_prefix.upper())
    pdb = checked_identifier(options.pdb.upper())
    schemas = [prefix, checked_identifier(prefix + '_TEST'),
               checked_identifier(prefix + '_E1_TEST'), checked_identifier(prefix + '_RUN')]
    if any(schema in PRESERVED for schema in schemas):
        raise ValueError('Las cuentas preservadas no pueden ser cuentas de validacion.')
    run_id = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).strftime('%Y-%m-%d_%H%M%S')
    evidence = ROOT / 'evidencias' / 'entrega2' / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    report = {'managed_by': 'tests/validar_entrega2.py', 'status': 'RUNNING',
              'run_id': run_id, 'schemas': schemas, 'service': options.service, 'pdb': pdb,
              'source_sha256': source_hashes(), 'tests': [], 'regression_e1': [],
              'bootstrap_complete': False}
    started = time.monotonic()
    oracledb.init_oracle_client(lib_dir=options.oracle_client_lib)
    try:
        with oracledb.connect(externalauth=True, mode=oracledb.AUTH_MODE_SYSDBA) as admin:
            cursor = admin.cursor()
            cursor.execute('ALTER SESSION SET CONTAINER=' + pdb)
            cursor.execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
            cursor.execute("SELECT banner_full FROM v$version WHERE banner_full LIKE 'Oracle Database%'")
            report.update(oracle=cursor.fetchone()[0], python=sys.version,
                          python_oracledb=oracledb.__version__, oracle_client=list(oracledb.clientversion()),
                          operating_system=platform.platform(),
                          base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
            original = {schema: schema_fingerprint(admin, schema) for schema in PRESERVED}
            if any(not value for value in original.values()):
                raise RuntimeError('Deben existir ambos esquemas que se conservan.')
            write_json(evidence / 'originales_antes.json', original)
            passwords = {schema: 'Uq' + secrets.token_hex(12) for schema in schemas}
            if options.resume_owned_run:
                previous_path = options.resume_owned_run.resolve()
                previous = json.loads((previous_path / 'resultado.json').read_text(encoding='utf-8'))
                if (previous.get('managed_by') != report['managed_by'] or previous.get('schemas') != schemas
                        or previous.get('service') != options.service or previous.get('pdb') != pdb
                        or not previous.get('bootstrap_complete')):
                    raise RuntimeError('La corrida no acredita bootstrap propio completo para estas cuentas.')
                # Los dos casos del certificador ya se ejecutaron antes de
                # instalar triggers; se reutilizan solo si su SQL no cambio.
                for name in ('scripts/verificar_entrega1.sql',):
                    if previous['source_sha256'][name] != report['source_sha256'][name]:
                        raise RuntimeError('Cambio la regresion del verificador; iniciar otro prefijo completo.')
                if original != json.loads((previous_path / 'originales_antes.json').read_text(encoding='utf-8')):
                    raise RuntimeError('Los esquemas preservados difieren de la corrida a reanudar.')
                for schema in schemas:
                    cursor.execute('SELECT created FROM dba_users WHERE username=:name', name=schema)
                    row = cursor.fetchone()
                    if not row or row[0].isoformat() != previous['accounts_created'][schema]:
                        raise RuntimeError('No se acredita la cuenta propia ' + schema)
                for schema in schemas:
                    cursor.execute(f'ALTER USER "{schema}" IDENTIFIED BY "{passwords[schema]}"')
                report['accounts_created'] = previous['accounts_created']
                report['regression_e1'] = [case for case in previous['regression_e1'] if case['id'] in ('I01', 'I02')]
                report['resumed_from'] = str(previous_path)
            else:
                report['accounts_created'] = {}
                for schema in schemas:
                    cursor.execute('SELECT COUNT(*) FROM dba_users WHERE username=:name', name=schema)
                    if cursor.fetchone()[0]:
                        raise RuntimeError('Se conserva la cuenta existente; elija otro prefijo: ' + schema)
                for schema in schemas:
                    cursor.execute(f'CREATE USER "{schema}" IDENTIFIED BY "{passwords[schema]}" DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP QUOTA UNLIMITED ON USERS')
                    cursor.execute(f'GRANT CREATE SESSION TO "{schema}"')
                    if schema != schemas[3]:
                        cursor.execute(f'GRANT CREATE TABLE, CREATE VIEW, CREATE MATERIALIZED VIEW, CREATE SEQUENCE, CREATE PROCEDURE, CREATE TRIGGER TO "{schema}"')
                        cursor.execute(f'ALTER USER "{schema}" QUOTA UNLIMITED ON TS_HISTORICO_RESERVAS')
                    cursor.execute('SELECT created FROM dba_users WHERE username=:name', name=schema)
                    report['accounts_created'][schema] = cursor.fetchone()[0].isoformat()
            runner = SqlPlusRunner(options.sqlplus, options.service, evidence, passwords,
                                   allow_compilation_warnings=True)

            def connect(schema=schemas[1], *, runtime=False):
                account = schemas[3] if runtime else schema
                connection = oracledb.connect(user=account, password=passwords[account], dsn=options.service)
                connection.call_timeout = 30000
                connection.cursor().execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
                connection.cursor().execute('ALTER SESSION SET ISOLATION_LEVEL=READ COMMITTED')
                if runtime:
                    connection.cursor().execute('ALTER SESSION SET CURRENT_SCHEMA=' + schemas[1])
                return connection

            if not options.resume_owned_run:
                print('Instalando modelo E1 anterior y carga en ' + schemas[0], flush=True)
                baseline = subprocess.check_output(['git', 'cat-file', 'blob', BASE_E1_COMMIT + ':01_DDL_TURISMOUQ_ORACLE21C.sql'], cwd=ROOT)
                baseline_path = evidence / 'ddl_base_entrega1.txt'
                baseline_path.write_bytes(baseline)
                runner.file(schemas[0], baseline_path, 'modelo_e1_antes_migracion')
                runner.file(schemas[0], '02_carga.sql', 'carga_academica')
                with connect(schemas[0]) as owner:
                    report['regression_e1'].extend(integrity_negative_tests(owner))
                for schema in schemas[1:3]:
                    runner.file(schema, '01_DDL_TURISMOUQ_ORACLE21C.sql', schema + '_modelo')
                for schema in schemas[:3]:
                    runner.file(schema, 'scripts/preparar_analitica.sql', schema + '_analitica')
            report['bootstrap_complete'] = True
            write_json(evidence / 'resultado.json', report)

            # Reintento solo sobre fixtures de una cuenta acreditada de esta corrida.
            if options.resume_owned_run:
                with connect() as test_owner:
                    discovered = {row[0] for row in test_owner.cursor().execute('SELECT table_name FROM user_tables')}
                    if discovered != set(MODEL_TABLES) | {'MV_OCUPACION_MENSUAL'}:
                        raise RuntimeError('La cuenta de fixtures contiene tablas ajenas.')
                    for table in MODEL_TABLES:
                        test_owner.cursor().execute('DELETE FROM ' + table)
                    test_owner.commit()
                    test_owner.cursor().execute("BEGIN DBMS_MVIEW.REFRESH('MV_OCUPACION_MENSUAL','C'); END;")
            before_migration = schema_fingerprint(admin, schemas[0])
            print('Instalando paquete y triggers; comprobando repeticion compatible.', flush=True)
            for schema in schemas[:2]:
                runner.file(schema, '04_instalar_capa_plsql.sql', schema + '_instalacion_1')
                runner.file(schema, '04_instalar_capa_plsql.sql', schema + '_instalacion_2')
            after_migration = schema_fingerprint(admin, schemas[0])
            if before_migration != after_migration:
                raise AssertionError('La migracion/instalacion modifico filas del modelo.')
            report['migration_data_preserved'] = {'status': 'PASS', 'tables': len(before_migration)}
            write_json(evidence / 'datos_esquema_entrega.json', after_migration)
            cursor.execute(f'GRANT EXECUTE ON "{schemas[1]}".PKG_TURISMOUQ TO "{schemas[3]}"')

            print('Ejecutando regresion analitica E1 y ocho consultas con E2 instalado.', flush=True)
            with connect(schemas[2]) as query_owner:
                report['regression_e1'].extend(run_query_tests(query_owner, ROOT, evidence))
            runner.file(schemas[0], '03_consultas_analisis.sql', 'ocho_consultas_con_e2')
            with connect(schemas[0]) as owner:
                report['regression_e1'].append(compare_parameter_clients(owner, runner, schemas[0]))
            if len(report['regression_e1']) != 23 or any(case['status'] != 'PASS' for case in report['regression_e1']):
                raise AssertionError('No pasaron los 23 casos de regresion E1.')
            write_json(evidence / 'regresion_entrega1.json', report['regression_e1'])

            def preservation():
                after = {schema: schema_fingerprint(admin, schema) for schema in PRESERVED}
                write_json(evidence / 'originales_despues.json', after)
                if after != original:
                    raise AssertionError('Se modifico un esquema preservado.')
                return {'status': 'PASS', 'expected': 'Conservar los dos esquemas originales',
                        'observed': {schema: {'tables': len(data), 'all_rows_identical': True}
                                     for schema, data in after.items()}}

            integration = {
                'I01': {'status': 'PASS', 'expected': 'Instalacion repetida compatible',
                        'observed': {'installation_runs': 2, 'schema': schemas[1]}},
                'I03': {'status': 'PASS', 'expected': 'Regresion E1 aprobada con nueva politica operativa',
                        'observed': {'cases': 23, 'sqlplus_queries': 8,
                                     'query_fixture_schema_without_e2_triggers': schemas[2],
                                     'report_schema_with_e2_triggers': schemas[0]}},
                'I04': preservation,
            }
            print('Ejecutando 40 casos E2, incluidas dos sesiones y fallos controlados.', flush=True)
            from probar_entrega2 import run_entrega2_tests
            with connect() as test_owner:
                report['tests'] = run_entrega2_tests(test_owner, connect, ROOT, evidence,
                                                    runtime_connection_factory=lambda: connect(runtime=True),
                                                    integration_results=integration)
            preservation()
            before_demo = schema_fingerprint(admin, schemas[0])
            runner.file(schemas[0], '05_demostracion_plsql.sql', 'demostracion_sustentacion')
            if schema_fingerprint(admin, schemas[0]) != before_demo:
                raise AssertionError('La demostracion no revirtio todas sus filas.')
            report['demonstration'] = {'status': 'PASS', 'model_tables_unchanged': len(before_demo),
                                       'script': '05_demostracion_plsql.sql'}
            runner.file(schemas[0], 'scripts/verificar_entrega1.sql', 'verificacion_datos_final')
            runner.file(schemas[0], 'scripts/verificar_entrega2.sql', 'verificacion_plsql_final')
            ids = [case['id'] for case in report['tests']]
            if len(ids) != 40 or len(set(ids)) != 40 or any(case['status'] != 'PASS' for case in report['tests']):
                raise AssertionError('La matriz E2 no termino con 40 casos unicos aprobados.')
            if report['source_sha256'] != source_hashes():
                raise AssertionError('Los archivos ejecutables cambiaron durante la corrida; repetir validacion.')
            report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = str(error)
        raise
    finally:
        report['duration_seconds'] = round(time.monotonic() - started, 2)
        write_json(evidence / 'resultado.json', report)
        print('Evidencia: ' + str(evidence), flush=True)
    print('APROBADA: 40 casos E2, 23 regresiones E1, ocho consultas y originales conservados.', flush=True)


if __name__ == '__main__':
    main()
