"""Pruebas numericas de las consultas reales en un esquema aislado vacio.

No crea usuarios/objetos ni acepta esquemas productivos. El propietario debe
terminar en _TEST y todas las tablas del modelo y la MV deben estar vacias.
Los escenarios revierten sus datos; solo M01 confirma para probar el refresco.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
import re
from typing import Any, Callable


MODEL_TABLES = (
    "HISTORICO_RESERVA", "PAGO", "RESENA", "AUDITORIA_TARIFA",
    "LIQUIDACION_MENSUAL", "RESERVA_HABITACION_TARIFA_APLICADA",
    "RESERVA_SERVICIO", "RESERVA_HABITACION", "RESERVA", "TARIFA",
    "ALOJAMIENTO_COMODIDAD", "SERVICIO", "HABITACION", "ALOJAMIENTO",
    "TEMPORADA", "COMODIDAD", "TIPO_HABITACION", "TIPO_ALOJAMIENTO",
    "MUNICIPIO", "CLIENTE", "PROPIETARIO", "USUARIO_SISTEMA",
)
QUERY_FILES = {
    1: "01_ocupacion_municipio_mes.sql",
    2: "02_ingresos_temporada.sql",
    3: "03_top_alojamientos.sql",
    4: "04_variacion_ingresos.sql",
    5: "05_consulta_parametrizada.sql",
    6: "06_ocupacion_materializada.sql",
    7: "07_composicion_ingresos.sql",
    8: "08_anticipacion_cancelaciones.sql",
}


def _statement(path: Path, plsql: bool = False) -> str:
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*--[^\n]*$", "", text).strip()
    if plsql:
        return re.sub(r"\s*/\s*$", "", text).strip()
    return text.rstrip(";").strip()


def _date(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text)


def _assert_equal(observed: Any, expected: Any, description: str) -> None:
    if observed != expected:
        raise AssertionError(f"{description}: esperado={expected!r}, observado={observed!r}")


def _assert_number(observed: Any, expected: float, description: str) -> None:
    if observed is None or not math.isclose(float(observed), expected, abs_tol=1e-8):
        raise AssertionError(f"{description}: esperado={expected}, observado={observed!r}")


def _json_default(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


class _Fixture:
    def __init__(self, connection: Any, repository: Path):
        self.connection = connection
        self.queries = {
            number: _statement(repository / "consultas" / name)
            for number, name in QUERY_FILES.items()
        }
        self.validation = _statement(
            repository / "scripts" / "validar_parametros_consulta.sql", plsql=True
        )

    def execute(self, sql: str, binds: dict | None = None) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, binds or {})

    def rows(self, sql: str, binds: dict | None = None) -> list[dict]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, binds or {})
            columns = [item[0].lower() for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def query(self, number: int, binds: dict | None = None) -> list[dict]:
        return self.rows(self.queries[number], binds)

    def counts(self) -> dict[str, int]:
        return {
            table: int(self.rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"])
            for table in MODEL_TABLES
        }

    def guard(self, require_empty: bool = True) -> str:
        owner = self.rows("SELECT USER AS owner FROM dual")[0]["owner"]
        if not owner.endswith("_TEST"):
            raise RuntimeError("Pruebas rechazadas: el usuario debe terminar en _TEST.")
        discovered = {
            row["table_name"] for row in self.rows("SELECT table_name FROM user_tables")
        }
        expected = set(MODEL_TABLES) | {"MV_OCUPACION_MENSUAL"}
        if discovered != expected:
            raise RuntimeError(
                "Pruebas rechazadas: se requieren las 22 tablas del modelo y su MV, "
                "sin tablas ajenas al escenario aislado."
            )
        if require_empty:
            populated = {name: count for name, count in self.counts().items() if count}
            mv_count = self.rows(
                "SELECT COUNT(*) AS n FROM mv_ocupacion_mensual"
            )[0]["n"]
            if populated or mv_count:
                raise RuntimeError("Pruebas rechazadas: el esquema o su MV contienen datos.")
        return owner

    def base(self, seasons: list[tuple] | None = None) -> None:
        for identifier, role in ((1, "PROPIETARIO"), (2, "CLIENTE")):
            self.execute(
                """INSERT INTO usuario_sistema
                   (id_usuario, username, password_hash, nombre_completo, email,
                    tipo_usuario, fecha_registro)
                   VALUES (:id, :username, 'HASH_FIXTURE', :name, :email,
                           :role, TIMESTAMP '2023-01-01 00:00:00')""",
                {"id": identifier, "username": f"fixture{identifier}",
                 "name": f"Usuario {identifier}", "email": f"fixture{identifier}@test.co",
                 "role": role},
            )
        self.execute(
            """INSERT INTO propietario
               (id_usuario, documento_identidad, telefono_contacto)
               VALUES (1, 'P001', '3000000001')"""
        )
        self.execute(
            """INSERT INTO cliente
               (id_usuario, tipo_documento, numero_documento, telefono)
               VALUES (2, 'CC', 'C001', '3000000002')"""
        )
        self.execute("INSERT INTO municipio (id_municipio, nombre) VALUES (1, 'Municipio prueba')")
        self.execute("INSERT INTO municipio (id_municipio, nombre) VALUES (2, 'Municipio sin oferta')")
        self.execute("INSERT INTO tipo_alojamiento (id_tipo_alojamiento, nombre) VALUES (1, 'Hotel')")
        self.execute(
            """INSERT INTO tipo_habitacion
               (id_tipo_habitacion, nombre, capacidad_estandar)
               VALUES (1, 'Doble', 2)"""
        )
        for identifier, name, municipality in ((1, "A", 1), (2, "B", 1), (3, "C sin oferta", 2)):
            self.lodging(identifier, name, municipality)
        for identifier, lodging in ((1, 1), (2, 1), (3, 2)):
            self.room(identifier, lodging)
        for identifier, start, end, kind in seasons or [
            (1, "2024-01-01", "2025-12-31", "BAJA")
        ]:
            self.execute(
                """INSERT INTO temporada
                   (id_temporada, nombre, fecha_inicio, fecha_fin, tipo_temporada)
                   VALUES (:id, :name, :start_date, :end_date, :kind)""",
                {"id": identifier, "name": f"Temporada {identifier}",
                 "start_date": _date(start), "end_date": _date(end), "kind": kind},
            )

    def lodging(self, identifier: int, name: str, municipality: int = 1) -> None:
        self.execute(
            """INSERT INTO alojamiento
               (id_alojamiento, id_propietario, id_municipio, id_tipo_alojamiento,
                nombre, direccion, telefono)
               VALUES (:id, 1, :municipality, 1, :name, 'Direccion fixture', '3000000000')""",
            {"id": identifier, "municipality": municipality, "name": name},
        )

    def room(self, identifier: int, lodging: int) -> None:
        self.execute(
            """INSERT INTO habitacion
               (id_habitacion, id_alojamiento, id_tipo_habitacion, numero_habitacion)
               VALUES (:id, :lodging, 1, :number_text)""",
            {"id": identifier, "lodging": lodging, "number_text": str(identifier)},
        )

    def reservation(self, identifier: int, start: str, end: str, amount: float,
                    room: int = 1, lodging: int = 1, status: str = "CONFIRMADA") -> None:
        self.execute(
            """INSERT INTO reserva
               (id_reserva, id_cliente, id_alojamiento, fecha_reserva,
                fecha_checkin, fecha_checkout, estado, valor_total)
               VALUES (:id, 2, :lodging, :reserved, :start_date, :end_date, :state, :amount)""",
            {"id": identifier, "lodging": lodging,
             "reserved": _date(start) - dt.timedelta(days=30),
             "start_date": _date(start), "end_date": _date(end),
             "state": status, "amount": amount},
        )
        self.execute(
            """INSERT INTO reserva_habitacion
               (id_reserva, id_habitacion, personas_hospedadas, precio_estadia_habitacion)
               VALUES (:id, :room_id, 1, :amount)""",
            {"id": identifier, "room_id": room, "amount": amount},
        )

    def segment(self, reservation: int, start: str, end: str, season: int,
                kind: str, price: float, room: int = 1) -> None:
        self.execute(
            """INSERT INTO reserva_habitacion_tarifa_aplicada
               (id_reserva, id_habitacion, fecha_inicio_tramo, fecha_fin_tramo,
                id_temporada, tipo_temporada_aplicado, precio_noche_aplicado, origen_dato)
               VALUES (:reservation_id, :room_id, :start_date, :end_date,
                       :season, :kind, :price, 'CAPTURADO')""",
            {"reservation_id": reservation, "room_id": room,
             "start_date": _date(start), "end_date": _date(end),
             "season": season, "kind": kind, "price": price},
        )

    def crossing(self) -> None:
        self.base([(1, "2025-06-01", "2025-06-30", "ALTA"),
                   (2, "2025-07-01", "2025-07-31", "BAJA")])
        self.reservation(1, "2025-06-29", "2025-07-03", 500)
        self.segment(1, "2025-06-29", "2025-07-01", 1, "ALTA", 100)
        self.segment(1, "2025-07-01", "2025-07-03", 2, "BAJA", 150)
        for season, price in ((1, 100), (2, 150)):
            self.execute(
                """INSERT INTO tarifa (id_tarifa, id_habitacion, id_temporada, precio_noche)
                   VALUES (:id, 1, :season, :price)""",
                {"id": season, "season": season, "price": price},
            )

    def occupancy(self, lodging: int, month: str) -> dict:
        return self.rows(
            """SELECT noches_ocupadas, noches_disponibles,
                      ROUND(pct_ocupacion, 2) AS porcentaje
               FROM vw_ocupacion_mensual_base
               WHERE id_alojamiento = :lodging AND mes = :month_date""",
            {"lodging": lodging, "month_date": _date(month)},
        )[0]

    def refresh(self) -> None:
        self.execute(
            """BEGIN DBMS_MVIEW.REFRESH(
                   list => 'MV_OCUPACION_MENSUAL', method => 'C',
                   atomic_refresh => TRUE); END;"""
        )

    def cleanup_committed(self) -> None:
        self.connection.rollback()
        self.guard(require_empty=False)
        for table in MODEL_TABLES:
            self.execute(f"DELETE FROM {table}")
        self.connection.commit()
        self.refresh()
        if any(self.counts().values()):
            raise AssertionError("Quedaron filas de fixtures despues de la limpieza.")
        _assert_equal(
            self.rows("SELECT COUNT(*) AS n FROM mv_ocupacion_mensual")[0]["n"],
            0, "MV vacia tras limpieza",
        )


def run_query_tests(connection: Any, repository_path: str | Path,
                    evidence_directory: str | Path) -> list[dict]:
    """Ejecuta 20 casos del plan y persiste solo sus resultados en JSON.

    P04 necesita otro cliente e I01/I02 pertenecen al verificador del ejecutor
    principal. Los 20 restantes se prueban aqui sobre archivos SQL reales.
    """
    repository = Path(repository_path).resolve()
    evidence = Path(evidence_directory).resolve()
    fixture = _Fixture(connection, repository)
    fixture.guard()
    original_autocommit = connection.autocommit
    connection.autocommit = False
    results: list[dict] = []

    def check(identifier: str, expected: Any, action: Callable[[], Any]) -> None:
        connection.rollback()
        try:
            observed = action()
            results.append({"id": identifier, "status": "PASS",
                            "expected": expected, "observed": observed})
        except Exception as error:
            results.append({"id": identifier, "status": "FAIL",
                            "expected": expected, "observed": str(error)})
        finally:
            connection.rollback()

    def parameters(single_day: bool = False) -> dict:
        fixture.base()
        fixture.reservation(1, "2025-06-01", "2025-06-02", 100)
        fixture.reservation(2, "2025-07-31", "2025-08-01", 100)
        fixture.reservation(3, "2025-08-01", "2025-08-02", 900)
        fixture.reservation(4, "2025-07-05", "2025-07-06", 800, status="CANCELADA")
        binds = {"fecha_ini": "2025-06-01",
                 "fecha_fin": "2025-06-01" if single_day else "2025-07-31"}
        fixture.execute(fixture.validation, binds)
        rows = fixture.query(5, binds)
        _assert_equal(len(rows), 1, "Alojamiento del informe parametrizado")
        _assert_equal(rows[0]["num_reservas"], 1 if single_day else 2, "Reservas del rango")
        _assert_number(rows[0]["ingreso_total"], 100 if single_day else 200, "Ingreso del rango")
        return {"binds": binds, "rows": rows}

    def invalid_parameters() -> list[dict]:
        variants = [
            (None, "2025-07-31", 20051),
            ("2025-6-01", "2025-07-31", 20052),
            ("2025-02-30", "2025-07-31", 20052),
            ("2025-07-31", "2025-06-01", 20053),
        ]
        observed = []
        for start, end, expected_code in variants:
            try:
                fixture.execute(fixture.validation, {"fecha_ini": start, "fecha_fin": end})
            except Exception as error:
                code = getattr(error.args[0], "code", None) if error.args else None
                _assert_equal(code, expected_code, "Codigo de entrada invalida")
                observed.append({"fecha_ini": start, "fecha_fin": end, "oracle_code": code})
            else:
                raise AssertionError("La validacion acepto un parametro invalido.")
        return observed

    def crossing() -> dict:
        fixture.crossing()
        rows = fixture.query(2)
        detail = {row["temporada"]: row["ingreso_hospedaje"]
                  for row in rows if row["nivel_agregacion"] == 0}
        _assert_equal(detail, {"ALTA": 200, "BAJA": 300}, "Distribucion capturada")
        total = next(row for row in rows if row["nivel_agregacion"] == 7)
        _assert_number(total["ingreso_hospedaje"], 500, "Total capturado")
        return {"detail": detail, "total": total}

    def historic_stability() -> dict:
        fixture.crossing()
        fixture.execute("UPDATE tarifa SET precio_noche = 120 WHERE id_temporada = 1")
        historical = next(row for row in fixture.query(2) if row["nivel_agregacion"] == 7)
        quote = fixture.rows(
            """SELECT SUM(
                       (LEAST(r.fecha_checkout, t.fecha_fin + 1)
                        - GREATEST(r.fecha_checkin, t.fecha_inicio)) * ta.precio_noche
                   ) AS importe
               FROM reserva r JOIN temporada t
                 ON t.fecha_inicio < r.fecha_checkout AND t.fecha_fin + 1 > r.fecha_checkin
               JOIN tarifa ta ON ta.id_temporada = t.id_temporada AND ta.id_habitacion = 1
               WHERE r.id_reserva = 1"""
        )[0]["importe"]
        _assert_number(historical["ingreso_hospedaje"], 500, "Ingreso historico")
        _assert_number(quote, 540, "Nueva valoracion desde catalogo")
        return {"historical": historical["ingreso_hospedaje"], "new_quote": quote}

    def legacy() -> dict:
        fixture.base()
        fixture.reservation(1, "2025-01-01", "2025-01-05", 500)
        rows = fixture.query(2)
        detail = next(row for row in rows if row["nivel_agregacion"] == 0)
        _assert_equal(detail["temporada"], "SIN DESGLOSE HISTORICO", "Categoria no inferida")
        _assert_number(detail["ingreso_hospedaje"], 500, "Importe legacy conservado")
        _assert_number(detail["importe_sin_desglose"], 500, "Importe pendiente")
        return detail

    def long_stay() -> dict:
        fixture.base()
        fixture.reservation(1, "2024-01-01", "2025-01-02", 3670)
        total = fixture.rows(
            """SELECT SUM(noches_ocupadas) AS noches
               FROM vw_ocupacion_mensual_base WHERE id_alojamiento = 1"""
        )[0]["noches"]
        january = fixture.occupancy(1, "2025-01-01")
        pivot = next(row for row in fixture.query(1)
                     if row["municipio"] == "Municipio prueba" and row["anio"] == 2025)
        _assert_number(total, 367, "Noches sin limite 366")
        _assert_number(january["noches_ocupadas"], 1, "Ultima noche enero 2025")
        _assert_number(pivot["ene"], 1.1, "Ocupacion municipal ultima noche")
        return {"total_nights": total, "january": january, "pivot_2025": pivot}

    def excluded_checkout() -> dict:
        fixture.base()
        fixture.reservation(1, "2025-01-31", "2025-02-01", 10)
        january = fixture.occupancy(1, "2025-01-01")
        february = fixture.occupancy(1, "2025-02-01")
        fixture.query(1)
        _assert_number(january["noches_ocupadas"], 1, "Enero")
        _assert_number(february["noches_ocupadas"], 0, "Checkout excluido de febrero")
        return {"january": january, "february": february}

    def capacity_percentages() -> dict:
        fixture.base()
        fixture.reservation(1, "2025-01-01", "2025-01-11", 100)
        a = fixture.occupancy(1, "2025-01-01")
        b = fixture.occupancy(2, "2025-01-01")
        pivot = next(row for row in fixture.query(1)
                     if row["municipio"] == "Municipio prueba" and row["anio"] == 2025)
        _assert_number(a["porcentaje"], 16.13, "Ocupacion A sobre 62 noches")
        _assert_number(b["porcentaje"], 0, "Ocupacion B")
        _assert_number(pivot["ene"], 10.8, "Porcentaje municipal sobre 93 noches")
        return {"A": a, "B": b, "municipality_january": pivot["ene"]}

    def zero_month() -> dict:
        fixture.base()
        fixture.reservation(1, "2025-01-01", "2025-01-11", 100)
        a = fixture.occupancy(1, "2025-02-01")
        b = fixture.occupancy(2, "2025-02-01")
        pivot = next(row for row in fixture.query(1)
                     if row["municipio"] == "Municipio prueba" and row["anio"] == 2025)
        _assert_number(a["porcentaje"], 0, "A febrero")
        _assert_number(b["porcentaje"], 0, "B febrero")
        _assert_number(pivot["feb"], 0, "Municipio febrero")
        return {"A": a, "B": b, "municipality_february": pivot["feb"]}

    def zero_inventory() -> dict:
        fixture.base()
        occupancy = fixture.occupancy(3, "2025-01-01")
        pivot = next(row for row in fixture.query(1)
                     if row["municipio"] == "Municipio sin oferta" and row["anio"] == 2025)
        _assert_number(occupancy["noches_disponibles"], 0, "Denominador cero")
        _assert_equal(occupancy["porcentaje"], None, "Porcentaje sin oferta")
        _assert_equal(pivot["ene"], None, "PIVOT sin oferta")
        return {"occupancy": occupancy, "municipality_january": pivot["ene"]}

    def monthly_lag() -> dict:
        fixture.base()
        fixture.reservation(1, "2025-01-01", "2025-01-02", 1000)
        fixture.reservation(2, "2025-03-01", "2025-03-02", 1500)
        rows = {row["mes"]: row for row in fixture.query(4)}
        february, march = rows["2025-02"], rows["2025-03"]
        _assert_number(february["variacion_absoluta"], -1000, "Febrero diferencia")
        _assert_number(february["variacion_pct"], -100, "Febrero porcentaje")
        _assert_number(march["ingreso_mes_anterior"], 0, "Marzo compara febrero")
        _assert_number(march["variacion_absoluta"], 1500, "Marzo diferencia")
        _assert_equal(march["variacion_pct"], None, "Marzo base cero")
        return {"february": february, "march": march}

    def annual_lag() -> dict:
        fixture.base()
        fixture.reservation(1, "2024-01-01", "2024-01-02", 100)
        fixture.reservation(2, "2025-01-01", "2025-01-02", 150)
        january = next(row for row in fixture.query(4) if row["mes"] == "2025-01")
        _assert_number(january["ingreso_mismo_mes_anio_ant"], 100, "Doce meses calendario")
        _assert_number(january["variacion_anual_pct"], 50, "Variacion anual")
        return january

    def rollup() -> list[dict]:
        fixture.crossing()
        rows = fixture.query(2)
        _assert_equal(len(rows), 5, "Dos detalles y tres niveles de subtotal")
        for level in (1, 3, 7):
            selected = [row for row in rows if row["nivel_agregacion"] == level]
            _assert_equal(len(selected), 1, f"Nivel GROUPING_ID {level}")
            _assert_number(selected[0]["ingreso_hospedaje"], 500, f"Subtotal nivel {level}")
        return rows

    def ranking() -> list[dict]:
        fixture.base()
        fixture.execute("UPDATE alojamiento SET id_municipio = 1, nombre = 'C' WHERE id_alojamiento = 3")
        fixture.lodging(4, "D")
        fixture.room(4, 3)
        fixture.room(5, 4)
        for identifier, amount, room, lodging in (
            (1, 500, 1, 1), (2, 400, 3, 2), (3, 300, 4, 3), (4, 300, 5, 4)
        ):
            fixture.reservation(identifier, "2025-01-01", "2025-01-02", amount,
                                room=room, lodging=lodging)
        rows = fixture.query(3)
        _assert_equal([row["puesto"] for row in rows], [1, 2, 3, 3], "RANK y empate")
        _assert_equal([row["ingreso_total"] for row in rows], [500, 400, 300, 300], "Orden de ingresos")
        return rows

    def unpivot(zero: bool = False) -> list[dict]:
        fixture.base()
        fixture.reservation(1, "2025-01-01", "2025-01-02", 0 if zero else 800)
        if not zero:
            fixture.execute(
                """INSERT INTO servicio
                   (id_servicio, id_alojamiento, nombre, precio_unitario)
                   VALUES (1, 1, 'Servicio fixture', 200)"""
            )
            fixture.execute(
                """INSERT INTO reserva_servicio
                   (id_reserva, id_servicio, cantidad, precio_unitario_aplicado, subtotal)
                   VALUES (1, 1, 1, 200, 200)"""
            )
            fixture.execute("UPDATE reserva SET valor_total = 1000 WHERE id_reserva = 1")
        rows = fixture.query(7)
        observed = {row["concepto"]: (row["valor"], row["pct_del_total"]) for row in rows}
        expected = {"HOSPEDAJE": (0, None), "SERVICIOS": (0, None)} if zero else {
            "HOSPEDAJE": (800, 80), "SERVICIOS": (200, 20)
        }
        _assert_equal(observed, expected, "Descomposicion UNPIVOT")
        return rows

    def business_crossing() -> list[dict]:
        fixture.crossing()
        rows = fixture.query(8)
        _assert_equal(len(rows), 1, "Una temporada por check-in")
        _assert_equal(rows[0]["tipo_temporada"], "ALTA", "Temporada del check-in")
        _assert_number(rows[0]["total_reservas"], 1, "Reserva contada una vez")
        _assert_number(rows[0]["noches_promedio"], 4, "Duracion completa")
        return rows

    def cancellations() -> list[dict]:
        fixture.base()
        for identifier in range(1, 11):
            start = _date("2025-01-01") + dt.timedelta(days=identifier * 2)
            fixture.reservation(
                identifier, start.date().isoformat(), (start + dt.timedelta(days=1)).date().isoformat(),
                10, status="CANCELADA" if identifier <= 2 else "CONFIRMADA",
            )
        rows = fixture.query(8)
        _assert_equal(len(rows), 1, "Grupo de temporada")
        _assert_number(rows[0]["total_reservas"], 10, "Incluye canceladas")
        _assert_number(rows[0]["canceladas"], 2, "Canceladas")
        _assert_number(rows[0]["pct_cancelacion"], 20, "Porcentaje cancelacion")
        return rows

    def materialization() -> dict:
        fixture.guard()
        fixture.base()
        fixture.reservation(1, "2025-12-01", "2025-12-11", 100)
        connection.commit()
        fixture.refresh()
        initial_rows = fixture.query(6)
        initial_a = next(row for row in initial_rows if row["alojamiento"] == "A")
        initial_b = next(row for row in initial_rows if row["alojamiento"] == "B")
        _assert_number(initial_a["pct_ocupacion_bruta"], 16.13, "MV A inicial")
        _assert_number(initial_b["pct_ocupacion_bruta"], 0, "MV conserva B cero")
        fixture.execute(
            """UPDATE reserva SET fecha_checkout = DATE '2025-12-21', valor_total = 200
               WHERE id_reserva = 1"""
        )
        fixture.execute(
            """UPDATE reserva_habitacion SET precio_estadia_habitacion = 200
               WHERE id_reserva = 1"""
        )
        connection.commit()
        stale = fixture.rows(
            """SELECT noches_ocupadas FROM mv_ocupacion_mensual
               WHERE id_alojamiento = 1 AND mes = DATE '2025-12-01'"""
        )[0]["noches_ocupadas"]
        source = fixture.occupancy(1, "2025-12-01")
        _assert_number(stale, 10, "MV retiene instantanea previa")
        _assert_number(source["noches_ocupadas"], 20, "Fuente actualizada")
        fixture.refresh()
        refreshed = fixture.rows(
            """SELECT noches_ocupadas FROM mv_ocupacion_mensual
               WHERE id_alojamiento = 1 AND mes = DATE '2025-12-01'"""
        )[0]["noches_ocupadas"]
        final_rows = fixture.query(6)
        _assert_number(refreshed, 20, "MV refrescada")
        _assert_equal([row["alojamiento"] for row in final_rows], ["B"], "Filtro menor a 30 tras refresco")
        differences = fixture.rows(
            """SELECT COUNT(*) AS n FROM (
                   (SELECT * FROM mv_ocupacion_mensual
                    MINUS SELECT * FROM vw_ocupacion_mensual_base)
                   UNION ALL
                   (SELECT * FROM vw_ocupacion_mensual_base
                    MINUS SELECT * FROM mv_ocupacion_mensual)
               )"""
        )[0]["n"]
        _assert_number(differences, 0, "Igualdad completa MV y fuente")
        return {"initial_query": initial_rows, "stale_nights": stale,
                "source_nights": source["noches_ocupadas"],
                "refreshed_nights": refreshed, "final_query": final_rows,
                "source_differences": differences}

    try:
        check("P01", {"reservations": 2, "income": 200}, parameters)
        check("P02", {"reservations": 1, "income": 100}, lambda: parameters(True))
        check("P03", {"null": 20051, "format": 20052, "invalid_date": 20052, "reversed": 20053}, invalid_parameters)
        check("H01", {"ALTA": 200, "BAJA": 300, "total": 500}, crossing)
        check("H02", {"historical": 500, "new_quote": 540}, historic_stability)
        check("H03", {"total": 500, "without_breakdown": 500}, legacy)
        check("O01", {"nights": 367, "january_2025_nights": 1}, long_stay)
        check("O02", {"january_nights": 1, "february_nights": 0}, excluded_checkout)
        check("O03", {"A": 16.13, "B": 0, "municipality": 10.8}, capacity_percentages)
        check("O04", {"A": 0, "B": 0, "municipality": 0}, zero_month)
        check("O05", {"available_nights": 0, "percentage": None}, zero_inventory)
        check("L01", {"february_change": -1000, "february_pct": -100,
                      "march_change": 1500, "march_pct": None}, monthly_lag)
        check("L02", {"previous_year": 100, "annual_pct": 50}, annual_lag)
        check("R01", {"detail": 500, "grouping_1": 500, "grouping_3": 500, "grouping_7": 500}, rollup)
        check("R02", {"ranks": [1, 2, 3, 3]}, ranking)
        check("U01", {"HOSPEDAJE": [800, 80], "SERVICIOS": [200, 20]}, unpivot)
        check("U02", {"HOSPEDAJE": [0, None], "SERVICIOS": [0, None]}, lambda: unpivot(True))
        check("N01", {"season": "ALTA", "reservations": 1, "nights": 4}, business_crossing)
        check("N02", {"reservations": 10, "cancelled": 2, "cancellation_pct": 20}, cancellations)
        check("M01", {"old_nights": 10, "new_nights": 20, "source_differences": 0}, materialization)
    finally:
        try:
            fixture.cleanup_committed()
            if results and results[-1]["id"] == "M01" and results[-1]["status"] == "PASS":
                results[-1]["observed"]["remaining_fixture_rows"] = 0
                results[-1]["observed"]["remaining_mv_rows"] = 0
        except Exception as error:
            results.append({"id": "LIMPIEZA", "status": "FAIL",
                            "expected": "22 tablas y MV vacias",
                            "observed": str(error)})
        finally:
            connection.autocommit = original_autocommit
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "pruebas_consultas.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2, default=_json_default) + "\n",
                encoding="utf-8",
            )
    return results
