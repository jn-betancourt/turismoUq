"""Mide los cuatro casos E3 antes y después de instalar los índices, sobre un esquema nuevo."""
import argparse
from datetime import date
from getpass import getpass
import os
from pathlib import Path
import secrets
import shutil
from statistics import median
import time

from validar_local import ROOT, SqlPlusRunner, checked_identifier, write_json


def measure(cursor, monitor, phase, run_id, name, filename, binds, repeats, evidence):
    sql = (ROOT / "consultas/entrega3" / filename).read_text(encoding="utf-8").strip()
    tag = f"E3_{run_id}_{phase}_{name}"
    sql = sql.replace("SELECT ", f"SELECT /*+ GATHER_PLAN_STATISTICS */ /* {tag} */ ", 1)
    cursor.execute(sql, binds)
    expected = cursor.fetchall()
    timings = []
    for _ in range(repeats):
        started = time.perf_counter()
        cursor.execute(sql, binds)
        rows = cursor.fetchall()
        timings.append((time.perf_counter() - started) * 1000)
        if rows != expected:
            raise AssertionError(f"Resultado no determinista en {name}.")

    monitor.execute(
        """SELECT sql_id, child_number, executions, buffer_gets, disk_reads, plan_hash_value
           FROM v$sql WHERE sql_text LIKE :tag AND executions >= :executions
           ORDER BY last_active_time DESC FETCH FIRST 1 ROW ONLY""",
        tag=f"SELECT /*+ GATHER_PLAN_STATISTICS */ /* {tag} */ %",
        executions=repeats + 1,
    )
    sql_id, child, executions, buffers, reads, plan_hash = monitor.fetchone()
    monitor.execute(
        """SELECT plan_table_output FROM TABLE(
               DBMS_XPLAN.DISPLAY_CURSOR(:sql_id, :child, 'ALLSTATS LAST +PREDICATE -PROJECTION'))""",
        sql_id=sql_id, child=child,
    )
    plan = "\n".join(line.rstrip() for (line,) in monitor).rstrip()
    if "A-Rows" not in plan or "Buffers" not in plan:
        raise AssertionError(f"No se capturaron estadísticas reales de {name}.")
    (evidence / f"{name}_{phase}.txt").write_text(plan + "\n", encoding="utf-8")
    monitor.execute(
        """SELECT DISTINCT object_name FROM v$sql_plan
           WHERE sql_id=:sql_id AND child_number=:child AND operation='INDEX' ORDER BY object_name""",
        sql_id=sql_id, child=child,
    )
    return expected, {
        "executions_including_warmup": executions,
        "median_ms": round(median(timings), 3),
        "buffer_gets_per_execution": round(buffers / executions, 2),
        "disk_reads_per_execution": round(reads / executions, 2),
        "plan_hash": plan_hash,
        "indexes": [index for (index,) in monitor],
        "result_rows": len(expected),
    }


def run_benchmark(owner, admin, install_indexes, evidence, repeats=15):
    run_id = secrets.token_hex(4)
    one_day = {"inicio": date(2025, 6, 15), "fin": date(2025, 6, 16)}
    cases = {
        "01_llegadas": ("01_llegadas_alojamiento.sql", {**one_day, "alojamiento": 27},
                        "IX_E3_RESERVA_ALOJ_CHECKIN"),
        "02_pagos_dia": ("02_pagos_por_dia.sql", one_day, "IX_E3_PAGO_DIA"),
        "03_salidas": ("03_salidas_para_liquidar.sql", one_day, "IX_E3_RESERVA_ESTADO_CHECKOUT"),
        "04_pagos_todo_el_periodo": ("02_pagos_por_dia.sql", {
            "inicio": date(2023, 1, 1), "fin": date(2027, 2, 1),
        }, None),
    }

    with owner.cursor() as cursor, admin.cursor() as monitor:
        cursor.execute("SELECT COUNT(*) FROM user_indexes WHERE index_name LIKE 'IX_E3_%'")
        if cursor.fetchone()[0]:
            raise RuntimeError("La línea base debe medirse en un esquema sin los índices E3.")
        for table in ("RESERVA", "PAGO"):
            cursor.execute("BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, :tab, cascade => TRUE); END;", tab=table)
        measurements = {}
        results_before = {}
        for phase in ("antes", "despues"):
            if phase == "despues":
                install_indexes()
            for name, (filename, binds, expected_index) in cases.items():
                rows, result = measure(cursor, monitor, phase, run_id, name, filename, binds, repeats, evidence)
                if phase == "antes":
                    results_before[name] = rows
                    measurements[name] = {"binds": binds, "antes": result}
                    continue
                if rows != results_before[name]:
                    raise AssertionError(f"El índice cambió las filas devueltas en {name}.")
                measurements[name]["despues"] = result
                measurements[name]["mismas_filas"] = True
                measurements[name]["resultado"] = [list(row) for row in rows]
                if expected_index and (
                    expected_index not in result["indexes"]
                    or result["buffer_gets_per_execution"] >= measurements[name]["antes"]["buffer_gets_per_execution"]
                ):
                    raise AssertionError(f"No se observó la mejora esperada en {name}: {measurements[name]}")
                if not expected_index and any(index.startswith("IX_E3_") for index in result["indexes"]):
                    raise AssertionError("El control de baja selectividad no conservó el acceso sin índice E3.")

    report = {"oracle": owner.version, "repetitions": repeats, "cases": measurements}
    write_json(evidence / "indices.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="TURISMOUQ_E3")
    parser.add_argument("--service", default="localhost:1521/xepdb1")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()

    import oracledb
    schema = checked_identifier(options.schema.upper())
    if not schema.startswith("TURISMOUQ_E3"):
        raise ValueError("Ejecuta en un esquema separado de Entrega 3.")
    password = os.environ.get("TURISMOUQ_E3_TEST_PASSWORD") or getpass(f"Contraseña de {schema}: ")
    sqlplus = shutil.which("sqlplus")
    if not sqlplus:
        raise RuntimeError("SQL*Plus debe estar en PATH.")
    oracledb.init_oracle_client(lib_dir=str(Path(sqlplus).parent))
    options.output.mkdir(parents=True, exist_ok=True)
    runner = SqlPlusRunner(sqlplus, options.service, options.output, {schema: password})
    with oracledb.connect(externalauth=True, mode=oracledb.AUTH_MODE_SYSDBA) as admin:
        admin.cursor().execute("ALTER SESSION SET CONTAINER=XEPDB1")
        with oracledb.connect(user=schema, password=password, dsn=options.service) as owner:
            run_benchmark(
                owner, admin,
                lambda: runner.file(schema, "07_crear_indices_entrega3.sql", "instalar_indices"),
                options.output,
            )
    print(f"Cuatro comparaciones guardadas en {options.output}.")


if __name__ == "__main__":
    main()
