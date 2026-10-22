"""Acceptance tests for the real PL/SQL package in an empty isolated schema.

Only the fixture owner ending in _TEST may own the 22 model tables and MV.
Temporary failure/barrier triggers are test instrumentation, never production
objects. The only autonomous transaction announces a concurrency barrier using
one reserved MUNICIPIO fixture row; cleanup verifies that it is removed.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable


_E1_SPEC = importlib.util.spec_from_file_location(
    "_turismouq_e1_fixture", Path(__file__).with_name("probar_consultas.py")
)
if _E1_SPEC is None or _E1_SPEC.loader is None:
    raise RuntimeError("No se pudo cargar la fixture compartida de Entrega 1.")
_E1 = importlib.util.module_from_spec(_E1_SPEC)
_E1_SPEC.loader.exec_module(_E1)

CASE_IDS = tuple(
    [f"F{number:02}" for number in range(1, 9)]
    + [f"R{number:02}" for number in range(1, 6)]
    + [f"C{number:02}" for number in range(1, 7)]
    + [f"T{number:02}" for number in range(1, 5)]
    + [f"A{number:02}" for number in range(1, 6)]
    + [f"L{number:02}" for number in range(1, 9)]
    + [f"I{number:02}" for number in range(1, 5)]
)
TEMPORARY_TRIGGER_NAMES = (
    "TRG_E2_TEST_RESERVA_FAIL", "TRG_E2_TEST_LIQUIDACION_FAIL", "TRG_E2_TEST_CAPTURE_BARRIER"
)
CONTRACT_TABLES = (
    "RESERVA", "RESERVA_HABITACION", "RESERVA_HABITACION_TARIFA_APLICADA",
    "RESERVA_SERVICIO", "PAGO", "RESENA", "LIQUIDACION_MENSUAL"
)
PRODUCTION_OBJECTS = {
    ("PKG_TURISMOUQ", "PACKAGE"), ("PKG_TURISMOUQ", "PACKAGE BODY"),
    ("TRG_AUDITAR_TARIFA", "TRIGGER"), ("TRG_RESERVA_HABITACION", "TRIGGER"),
    ("TRG_RESERVA", "TRIGGER"),
}
COMMISSION_CRITERION = "FINALIZADA_CHECKOUT_HMAS_SERV_V1"


def _date(value: str | dt.datetime | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if isinstance(value, str) else value


def _equal(observed: Any, expected: Any, label: str) -> None:
    if observed != expected:
        raise AssertionError(f"{label}: esperado={expected!r}, observado={observed!r}")


def _money(observed: Any, expected: Any, label: str) -> None:
    if observed is None or Decimal(str(observed)) != Decimal(str(expected)):
        raise AssertionError(f"{label}: esperado={expected!r}, observado={observed!r}")


def _oracle_code(error: Exception) -> int | None:
    return getattr(error.args[0], "code", None) if error.args else None


def _expect_error(action: Callable[[], Any], expected: int | set[int], label: str) -> dict:
    allowed = {expected} if isinstance(expected, int) else expected
    try:
        action()
    except Exception as error:
        code = _oracle_code(error)
        if code not in allowed:
            raise AssertionError(
                f"{label}: se esperaba {sorted(allowed)}, obtenido {code}: {error}"
            ) from error
        return {"scenario": label, "oracle_code": code}
    raise AssertionError(f"{label}: la operacion fue aceptada y debia rechazarse.")


def _json_default(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return _E1._json_default(value)


class _Fixture(_E1._Fixture):
    def __init__(self, connection: Any, repository: Path):
        super().__init__(connection, repository)
        self.owner = str(self.rows("SELECT USER AS owner FROM dual")[0]["owner"])
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*_TEST", self.owner):
            raise RuntimeError("El propietario de pruebas debe ser un identificador aislado terminado en _TEST.")
        self.package = f'"{self.owner}".pkg_turismouq'
        self.temporary_triggers: set[str] = set()

    def guard(self, require_empty: bool = True) -> str:
        owner = super().guard(require_empty)
        temporary = self.rows(
            "SELECT trigger_name FROM user_triggers WHERE trigger_name IN "
            "('TRG_E2_TEST_RESERVA_FAIL','TRG_E2_TEST_LIQUIDACION_FAIL','TRG_E2_TEST_CAPTURE_BARRIER')"
        )
        if temporary:
            raise RuntimeError("Hay instrumentacion temporal de otra corrida; no se reemplaza automaticamente.")
        return owner

    def base(self, seasons: list[tuple] | None = None, prices: dict | None = None) -> None:
        super().base(seasons or [(1, "2024-01-01", "2026-12-31", "BAJA")])
        season_rows = self.rows("SELECT id_temporada FROM temporada ORDER BY id_temporada")
        identifier = 0
        for room in (1, 2, 3):
            for season in season_rows:
                identifier += 1
                season_id = int(season["id_temporada"])
                price = (prices or {}).get((room, season_id), (prices or {}).get(room, 100))
                self.execute(
                    "INSERT INTO tarifa(id_tarifa,id_habitacion,id_temporada,precio_noche) "
                    "VALUES(:id,:room_id,:season_id,:price)",
                    {"id": identifier, "room_id": room, "season_id": season_id, "price": price},
                )
        for identifier, lodging, price in ((1, 1, 20), (2, 1, 40), (3, 2, 10)):
            self.execute(
                "INSERT INTO servicio(id_servicio,id_alojamiento,nombre,precio_unitario) "
                "VALUES(:id,:lodging,:name,:price)",
                {"id": identifier, "lodging": lodging, "name": f"Servicio {identifier}", "price": price},
            )

    def crossing_base(self) -> None:
        self.base([(1, "2025-06-01", "2025-06-30", "ALTA"),
                   (2, "2025-07-01", "2025-07-31", "BAJA")],
                  {(room, 2): 150 for room in (1, 2, 3)})

    def quote(self, start: str | dt.datetime | None, end: str | dt.datetime | None,
              room: int | None = 1, connection: Any = None) -> Any:
        target = connection or self.connection
        with target.cursor() as cursor:
            output = cursor.var(float)
            cursor.execute(
                f"BEGIN :amount := {self.package}.fn_valor_estadia(:room_id,:date_in,:date_out); END;",
                amount=output, room_id=room, date_in=_date(start), date_out=_date(end),
            )
            return output.getvalue()

    def create(self, start: str | dt.datetime | None = "2025-06-01",
               end: str | dt.datetime | None = "2025-06-02", *,
               rooms: list[tuple] | None = None, services: list[tuple] | None = None,
               customer: int | None = 2, lodging: int | None = 1,
               connection: Any = None) -> dict:
        target = connection or self.connection
        room_requests = [(1, 1)] if rooms is None else rooms
        service_requests = [] if services is None else services
        assignments = []
        binds: dict[str, Any] = {
            "customer": customer, "lodging": lodging, "date_in": _date(start), "date_out": _date(end)
        }
        for index, (room, people) in enumerate(room_requests, 1):
            assignments += [f"v_rooms({index}).id_habitacion := :room_{index};",
                            f"v_rooms({index}).personas_hospedadas := :people_{index};"]
            binds[f"room_{index}"], binds[f"people_{index}"] = room, people
        for index, (service, quantity) in enumerate(service_requests, 1):
            assignments += [f"v_services({index}).id_servicio := :service_{index};",
                            f"v_services({index}).cantidad := :quantity_{index};"]
            binds[f"service_{index}"], binds[f"quantity_{index}"] = service, quantity
        with target.cursor() as cursor:
            reservation_id, amount = cursor.var(int), cursor.var(float)
            binds.update(reservation_id=reservation_id, total_amount=amount)
            cursor.execute(
                f"""DECLARE
                    v_rooms {self.package}.lista_solicitudes_habitacion := {self.package}.lista_solicitudes_habitacion();
                    v_services {self.package}.lista_solicitudes_servicio := {self.package}.lista_solicitudes_servicio();
                BEGIN
                    v_rooms.EXTEND({len(room_requests)});
                    v_services.EXTEND({len(service_requests)});
                    {' '.join(assignments)}
                    {self.package}.sp_crear_reserva(:customer,:lodging,:date_in,:date_out,
                        v_rooms,v_services,:reservation_id,:total_amount);
                END;""", binds,
            )
            return {"id_reserva": int(reservation_id.getvalue()), "valor_total": amount.getvalue()}

    def liquidate(self, year: Any = 2025, month: Any = 2, percentage: Any = 12,
                  lodging: Any = None, connection: Any = None) -> dict:
        target = connection or self.connection
        with target.cursor() as cursor:
            created, preserved = cursor.var(int), cursor.var(int)
            cursor.execute(
                f"BEGIN {self.package}.sp_liquidar_mes(:year_value,:month_value,:percentage,:lodging,"
                ":created,:preserved); END;",
                year_value=year, month_value=month, percentage=percentage, lodging=lodging,
                created=created, preserved=preserved,
            )
            return {"created": int(created.getvalue()), "preserved": int(preserved.getvalue())}

    def contract_counts(self) -> dict:
        return {name: self.rows(f"SELECT COUNT(*) n FROM {name}")[0]["n"] for name in CONTRACT_TABLES}

    def segments(self, reservation: int) -> list[dict]:
        return self.rows(
            "SELECT id_habitacion,fecha_inicio_tramo,fecha_fin_tramo,id_temporada,"
            "tipo_temporada_aplicado,precio_noche_aplicado,origen_dato "
            "FROM reserva_habitacion_tarifa_aplicada WHERE id_reserva=:id "
            "ORDER BY id_habitacion,fecha_inicio_tramo", {"id": reservation},
        )

    def completed(self, start: str = "2025-01-31", end: str = "2025-02-01", **kwargs: Any) -> dict:
        reservation = self.create(start, end, **kwargs)
        self.execute("UPDATE reserva SET estado='FINALIZADA' WHERE id_reserva=:id",
                     {"id": reservation["id_reserva"]})
        return reservation

    def temporary_trigger(self, name: str, definition: str) -> None:
        if name not in TEMPORARY_TRIGGER_NAMES:
            raise RuntimeError("Nombre de trigger temporal no autorizado.")
        self.execute(f"CREATE TRIGGER {name} {definition}")
        self.temporary_triggers.add(name)

    def drop_temporary_triggers(self) -> None:
        self.connection.rollback()
        for name in sorted(self.temporary_triggers):
            self.execute(f"DROP TRIGGER {name}")
            self.temporary_triggers.remove(name)

    def cleanup(self) -> dict:
        self.drop_temporary_triggers()
        super().cleanup_committed()
        self.guard()
        return {"fixture_rows": 0, "materialized_rows": 0, "temporary_triggers": 0}


class _Worker:
    """A real second Oracle session with bounded completion and cancellation."""
    def __init__(self, factory: Callable[[], Any], fixture: _Fixture, action: Callable[[Any], Any]):
        self.factory, self.fixture, self.action = factory, fixture, action
        self.started, self.finished = threading.Event(), threading.Event()
        self.connection: Any = None
        self.result: Any = None
        self.error: Exception | None = None
        self.elapsed = 0.0
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        started_at = time.monotonic()
        try:
            self.connection = self.factory()
            self.connection.autocommit = False
            self.connection.call_timeout = 15000
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT USER FROM dual")
                _equal(cursor.fetchone()[0], self.fixture.owner, "Propietario de la segunda conexion")
                cursor.execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
            self.started.set()
            self.result = self.action(self.connection)
        except Exception as error:
            self.error = error
        finally:
            try:
                if self.connection is not None:
                    try:
                        self.connection.rollback()
                    finally:
                        self.connection.close()
            except Exception as cleanup_error:
                if self.error is None:
                    self.error = cleanup_error
            finally:
                self.elapsed = time.monotonic() - started_at
                self.finished.set()

    def start(self) -> "_Worker":
        self.thread.start()
        if not self.started.wait(10):
            self.finish()
            raise AssertionError("La segunda conexion no inicio dentro del plazo.")
        return self

    def assert_waiting(self) -> None:
        if self.finished.wait(0.25):
            if self.error:
                raise AssertionError(f"La segunda sesion no espero el bloqueo: {self.error}") from self.error
            raise AssertionError("La segunda sesion termino antes de liberar el recurso comun.")

    def finish(self, expected_error: int | None = None) -> Any:
        if not self.finished.wait(20):
            if self.connection is not None:
                self.connection.cancel()
            if not self.finished.wait(5):
                raise RuntimeError("La segunda sesion no termino ni tras cancelar su llamada.")
            raise AssertionError("La segunda sesion excedio el plazo de la prueba.")
        if expected_error is not None:
            if self.error is None:
                raise AssertionError(f"Se esperaba ORA-{expected_error}; la segunda sesion fue aceptada.")
            _equal(_oracle_code(self.error), expected_error, "Error de la segunda sesion")
            return {"oracle_code": expected_error, "elapsed_seconds": round(self.elapsed, 3)}
        if self.error:
            raise self.error
        return self.result


def run_entrega2_tests(connection: Any, connection_factory: Callable[[], Any],
                      repository_path: str | Path, evidence_directory: str | Path,
                      runtime_connection_factory: Callable[[], Any] | None = None,
                      integration_results: dict | None = None) -> list[dict]:
    """Run all 40 IDs; external I01/I03/I04 evidence is mandatory, never skipped.

    Factories open independent connections. The owner factory must connect to
    the same isolated _TEST owner. Runtime has EXECUTE only. integration_results
    contains real I01/I03 dictionaries and an I04 dictionary or zero-arg callback.
    Each dictionary must contain status, expected and observed. Root verifies
    preserved-schema fingerprints again after this module returns.
    """
    repository, evidence = Path(repository_path).resolve(), Path(evidence_directory).resolve()
    fixture = _Fixture(connection, repository)
    fixture.guard()
    previous_autocommit = connection.autocommit
    connection.autocommit = False
    fixture.execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
    evidence.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    workers: list[_Worker] = []

    def persist() -> None:
        temporary = evidence / "pruebas_entrega2.json.tmp"
        temporary.write_text(
            json.dumps(results, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8"
        )
        temporary.replace(evidence / "pruebas_entrega2.json")

    def owner_connection() -> Any:
        other = connection_factory()
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT USER FROM dual")
                _equal(cursor.fetchone()[0], fixture.owner, "Propietario de la conexion observadora")
            return other
        except Exception:
            other.close()
            raise

    def external(identifier: str) -> dict:
        value = (integration_results or {}).get(identifier)
        if callable(value):
            value = value()
        if not isinstance(value, dict) or value.get("status") != "PASS" or "observed" not in value:
            raise AssertionError(f"{identifier}: falta evidencia externa real aprobada del ejecutor.")
        return value["observed"]

    def worker(action: Callable[[Any], Any]) -> _Worker:
        item = _Worker(connection_factory, fixture, action)
        workers.append(item)
        return item.start()

    def commit_create(other: Any, **kwargs: Any) -> dict:
        value = fixture.create(connection=other, **kwargs)
        other.commit()
        return value

    def isolated_error(action: Callable[[], Any], code: int, label: str) -> dict:
        fixture.execute("SAVEPOINT e2_expected_error")
        try:
            return _expect_error(action, code, label)
        finally:
            fixture.execute("ROLLBACK TO e2_expected_error")

    def basic_quote(start: str, end: str, expected: Any, price: Any = 100) -> dict:
        fixture.base(prices={1: price})
        before = fixture.counts()
        amount = fixture.quote(start, end)
        _money(amount, expected, "Cotizacion")
        _equal(fixture.counts(), before, "Funcion sin escrituras")
        return {"amount": amount, "written_rows": 0}

    def crossing() -> dict:
        fixture.crossing_base()
        before = fixture.counts()
        amount = fixture.quote("2025-06-29", "2025-07-03")
        _money(amount, 500, "Cruce de temporadas")
        _equal(fixture.counts(), before, "Cotizacion sin escrituras")
        reservation = fixture.create("2025-06-29", "2025-07-03")
        segments = fixture.segments(reservation["id_reserva"])
        _equal(len(segments), 2, "Dos tramos capturados")
        _equal([(s["fecha_fin_tramo"] - s["fecha_inicio_tramo"]).days for s in segments], [2, 2], "Noches por tramo")
        _equal([s["precio_noche_aplicado"] for s in segments], [100, 150], "Precios contratados")
        return {"amount": amount, "segments": segments}

    def excluded_checkout() -> dict:
        fixture.crossing_base()
        value = fixture.quote("2025-06-30", "2025-07-01")
        _money(value, 100, "Checkout excluido")
        return {"amount": value}

    def invalid_dates() -> dict:
        fixture.base()
        observed = []
        for start, end, code in (
            (None, "2025-06-02", 20302), ("2025-06-01", None, 20302),
            ("2025-06-01T01:00:00", "2025-06-02", 20302),
            ("2025-06-01", "2025-06-02T01:00:00", 20302),
            ("2025-06-01", "2025-06-01", 20301),
            ("2025-06-02", "2025-06-01", 20301),
            ("9999-12-30", "9999-12-31", 20302),
        ):
            before = fixture.counts()
            observed.append(_expect_error(lambda a=start, b=end: fixture.quote(a, b), code, f"Fechas {start}/{end}"))
            _equal(fixture.counts(), before, "Error de funcion sin escritura")
        return {"cases": observed, "written_rows": 0}

    def coverage_errors() -> dict:
        observed = []
        scenarios = [
            ("hueco", [(1,"2025-06-01","2025-06-29","ALTA"),(2,"2025-07-01","2025-07-31","BAJA")], 20308),
            ("superposicion", [(1,"2025-06-01","2025-07-01","ALTA"),(2,"2025-07-01","2025-07-31","BAJA")], 20309),
            ("tarifa ausente", [(1,"2025-06-01","2025-06-30","ALTA"),(2,"2025-07-01","2025-07-31","BAJA")], 20310),
            ("temporada con hora", [(1,"2025-06-01T01:00:00","2025-06-30","ALTA"),(2,"2025-07-01","2025-07-31","BAJA")], 20302),
            ("hueco y superposicion compensados", [(1,"2025-06-29","2025-06-29","ALTA"),
                (2,"2025-07-01","2025-07-02","MEDIA"),(3,"2025-07-02","2025-07-02","BAJA")], {20308,20309}),
        ]
        for label, seasons, code in scenarios:
            connection.rollback()
            fixture.base(seasons)
            if label == "tarifa ausente":
                fixture.execute("DELETE FROM tarifa WHERE id_habitacion=1 AND id_temporada=2")
            before = fixture.counts()
            observed.append(_expect_error(lambda: fixture.quote("2025-06-29","2025-07-03"), code, label))
            _equal(fixture.counts(), before, "Cobertura rechazada sin escribir")
        return {"cases": observed}

    def historical_price() -> dict:
        fixture.crossing_base()
        reservation = fixture.create("2025-06-29", "2025-07-03")
        old_segments = fixture.segments(reservation["id_reserva"])
        fixture.execute("UPDATE tarifa SET precio_noche=120 WHERE id_habitacion=1 AND id_temporada=1")
        new_quote = fixture.quote("2025-06-29", "2025-07-03")
        _money(new_quote, 540, "Cotizacion nueva")
        _equal(fixture.segments(reservation["id_reserva"]), old_segments, "Tramos historicos inmutables")
        _money(fixture.rows("SELECT valor_total FROM reserva WHERE id_reserva=:id", {"id":reservation["id_reserva"]})[0]["valor_total"], 500, "Contrato anterior")
        return {"historical":500, "new_quote":new_quote, "segments":old_segments}

    def monetary_overflow() -> dict:
        fixture.base(prices={1:Decimal("9999999999.99")})
        before = fixture.contract_counts()
        observed = [_expect_error(lambda:fixture.quote("2025-06-01","2025-06-03"),20311,"Cotizacion fuera de capacidad"),
                    _expect_error(lambda:fixture.create("2025-06-01","2025-06-03"),20311,"Reserva fuera de capacidad")]
        _equal(fixture.contract_counts(),before,"Overflow sin contrato parcial")
        return {"cases":observed,"partial_rows":0}

    def reservation_totals() -> dict:
        fixture.base(prices={2:150})
        result=fixture.create("2025-06-01","2025-06-05",rooms=[(1,2),(2,1)],services=[(1,3),(2,1)])
        _money(result["valor_total"],1100,"Total de reserva")
        details=fixture.rows("SELECT precio_estadia_habitacion importe FROM reserva_habitacion ORDER BY id_habitacion")
        _equal([r["importe"] for r in details],[400,600],"Importes por habitacion")
        _equal([r["subtotal"] for r in fixture.rows("SELECT subtotal FROM reserva_servicio ORDER BY id_servicio")],[60,40],"Servicios")
        _equal({r["origen_dato"] for r in fixture.segments(result["id_reserva"])},{"CAPTURADO"},"Procedencia")
        _equal(fixture.rows("SELECT estado FROM reserva")[0]["estado"],"PENDIENTE","Estado inicial")
        _equal(fixture.rows("SELECT COUNT(*) n FROM pago")[0]["n"],0,"Sin cobro automatico")
        return {"reservation":result,"room_amounts":details,"services":[60,40],"payments":0}

    def capacity() -> dict:
        fixture.base()
        accepted=fixture.create(rooms=[(1,2)])
        before=fixture.contract_counts()
        observed=[]
        for people, code in ((3,20305),(1.5,20307),(0,20307),(-1,20307),(None,20307)):
            observed.append(_expect_error(lambda p=people:fixture.create("2025-06-10","2025-06-11",rooms=[(2,p)]),code,f"Personas {people}"))
        for quantity in (1.5,0,-1,None):
            observed.append(_expect_error(lambda q=quantity:fixture.create("2025-06-10","2025-06-11",rooms=[(2,1)],services=[(1,q)]),20307,f"Cantidad {quantity}"))
        _equal(fixture.contract_counts(),before,"Rechazos sin residuos")
        return {"exact_capacity":accepted,"rejected":observed}

    def invalid_references() -> dict:
        fixture.base()
        observed=[]
        variants=[("habitacion inexistente",{"rooms":[(999,1)]},20303),
                  ("habitacion duplicada",{"rooms":[(1,1),(1,1)]},20307),
                  ("habitaciones vacias",{"rooms":[]},20307),
                  ("otra sede",{"rooms":[(3,1)]},20306),
                  ("cliente inexistente",{"customer":999},20306),
                  ("alojamiento inexistente",{"lodging":999},20306),
                  ("servicio inexistente",{"services":[(999,1)]},20313),
                  ("servicio de otra sede",{"services":[(3,1)]},20313),
                  ("servicio duplicado",{"services":[(1,1),(1,2)]},20307)]
        for label, kwargs, code in variants:
            before=fixture.contract_counts()
            observed.append(_expect_error(lambda k=kwargs:fixture.create(**k),code,label))
            _equal(fixture.contract_counts(),before,"Referencia rechazada sin residuos")
        for state in ("MANTENIMIENTO","FUERA_SERVICIO"):
            fixture.execute("UPDATE habitacion SET estado=:state WHERE id_habitacion=1",{"state":state})
            observed.append(_expect_error(lambda:fixture.create(),20304,state))
        fixture.execute("UPDATE habitacion SET estado='DISPONIBLE' WHERE id_habitacion=1")
        fixture.create()
        before=fixture.contract_counts()
        observed.append(_expect_error(lambda:fixture.create("2025-06-01","2025-06-01"),20301,"Fecha invalida antes del solape"))
        _equal(fixture.contract_counts(),before,"Error prioritario sin residuos")
        return {"cases":observed}

    def reservation_partial_rollback() -> dict:
        fixture.base()
        fixture.temporary_trigger("TRG_E2_TEST_RESERVA_FAIL", """BEFORE INSERT ON reserva_servicio FOR EACH ROW
            BEGIN RAISE_APPLICATION_ERROR(-20991,'Fallo controlado despues de los detalles'); END;""")
        fixture.execute("INSERT INTO municipio(id_municipio,nombre) VALUES(900,'Marcador previo R04')")
        error=_expect_error(lambda:fixture.create(services=[(1,1)]),20991,"Fallo despues de detalles")
        _equal(fixture.contract_counts(),{name:0 for name in CONTRACT_TABLES},"Rollback completo de la llamada")
        _equal(fixture.rows("SELECT COUNT(*) n FROM municipio WHERE id_municipio=900")[0]["n"],1,"Trabajo previo conservado")
        other=owner_connection()
        try:
            with other.cursor() as cursor:
                cursor.execute(f'SELECT COUNT(*) FROM "{fixture.owner}".municipio WHERE id_municipio=900')
                _equal(cursor.fetchone()[0],0,"Trabajo previo no confirmado")
        finally:
            other.close()
        return {"error":error,"partial_rows":0,"prior_work_visible_to_caller":1,"prior_work_committed":False}

    def reservation_caller_rollback() -> dict:
        fixture.base()
        connection.commit()
        result=fixture.create(services=[(1,1)])
        connection.rollback()
        _equal(fixture.contract_counts(),{name:0 for name in CONTRACT_TABLES},"Rollback del llamador")
        return {"created_before_rollback":result,"remaining_contract_rows":0}

    def concurrent_reservation(first_commit: bool) -> dict:
        fixture.base()
        connection.commit()
        first=fixture.create()
        second=worker(lambda c:commit_create(c))
        try:
            second.assert_waiting()
            connection.commit() if first_commit else connection.rollback()
            observed=second.finish(20304 if first_commit else None)
        finally:
            connection.rollback()
        _equal(fixture.rows("SELECT COUNT(*) n FROM reserva")[0]["n"],1,"Una reserva persistida")
        return {"first":first,"first_committed":first_commit,"second":observed,"persisted":1}

    def lock_timeout() -> dict:
        fixture.base()
        connection.commit()
        fixture.execute("SELECT id_habitacion FROM habitacion WHERE id_habitacion=1 FOR UPDATE")
        second=worker(lambda c:fixture.create(connection=c))
        try:
            observed=second.finish(20312)
            if second.elapsed < 4:
                raise AssertionError("No se observo la espera configurada antes del timeout.")
        finally:
            connection.rollback()
        _equal(fixture.rows("SELECT COUNT(*) n FROM reserva")[0]["n"],0,"Timeout sin reserva")
        return observed

    def independent_and_reversed() -> dict:
        fixture.base()
        connection.commit()
        fixture.create(rooms=[(1,1)])
        independent=worker(lambda c:commit_create(c,rooms=[(2,1)]))
        try:
            independent_result=independent.finish()
        finally:
            connection.rollback()
        fixture.create("2025-06-10","2025-06-11",rooms=[(2,1),(1,1)])
        reversed_worker=worker(lambda c:commit_create(c,start="2025-06-10",end="2025-06-11",rooms=[(1,1),(2,1)]))
        try:
            reversed_worker.assert_waiting()
            connection.rollback()
            reversed_result=reversed_worker.finish()
        finally:
            connection.rollback()
        return {"independent":independent_result,"reverse_order":reversed_result,"deadlocks":0}

    def concurrent_price_capture() -> dict:
        fixture.base()
        fixture.temporary_trigger("TRG_E2_TEST_CAPTURE_BARRIER", """BEFORE INSERT ON reserva_habitacion FOR EACH ROW
            DECLARE
                v_service NUMBER;
                PROCEDURE announce_capture IS
                    PRAGMA AUTONOMOUS_TRANSACTION;
                BEGIN
                    INSERT INTO municipio(id_municipio,nombre) VALUES(990,'Barrera de captura C05');
                    COMMIT;
                END;
            BEGIN
                announce_capture;
                SELECT id_servicio INTO v_service FROM servicio WHERE id_servicio=1 FOR UPDATE WAIT 10;
            END;""")
        fixture.execute("SELECT id_servicio FROM servicio WHERE id_servicio=1 FOR UPDATE")
        second=worker(lambda c:commit_create(c,start="2025-06-01",end="2025-06-05"))
        deadline=time.monotonic()+10
        try:
            while time.monotonic()<deadline:
                if fixture.rows("SELECT COUNT(*) n FROM municipio WHERE id_municipio=990")[0]["n"]:
                    break
                if second.finished.wait(0.02):
                    second.finish()
                    raise AssertionError("La llamada termino sin alcanzar la barrera de captura.")
            else:
                raise AssertionError("No se observo la barrera posterior a la captura de precios.")
            fixture.execute("UPDATE tarifa SET precio_noche=120 WHERE id_habitacion=1")
            connection.commit()
            result=second.finish()
        finally:
            connection.rollback()
        segments=fixture.segments(result["id_reserva"])
        _money(result["valor_total"],400,"Contrato capturado antes del cambio concurrente")
        _equal([row["precio_noche_aplicado"] for row in segments],[100],"Tramos de la misma captura")
        _money(fixture.quote("2025-06-01","2025-06-05"),480,"Catalogo nuevo")
        return {"barrier_observed":True,"contract":result,"captured_price":100,"new_quote":480}

    def concurrent_header_detail() -> dict:
        fixture.base()
        fixture.execute("INSERT INTO reserva(id_reserva,id_cliente,id_alojamiento,fecha_checkin,fecha_checkout,estado,valor_total) VALUES(800,2,1,DATE '2025-06-01',DATE '2025-06-02','PENDIENTE',100)")
        fixture.reservation(801,"2025-06-10","2025-06-12",200)
        connection.commit()
        fixture.execute("INSERT INTO reserva_habitacion VALUES(800,1,1,100)")
        def update_header(other: Any) -> None:
            with other.cursor() as cursor:
                cursor.execute("UPDATE reserva SET fecha_checkin=DATE '2025-06-10',fecha_checkout=DATE '2025-06-12' WHERE id_reserva=800")
            other.commit()
        second=worker(update_header)
        try:
            second.assert_waiting()
            connection.commit()
            error=second.finish(20304)
        finally:
            connection.rollback()
        header=fixture.rows("SELECT fecha_checkin,fecha_checkout FROM reserva WHERE id_reserva=800")[0]
        _equal(header["fecha_checkin"],_date("2025-06-01"),"Fecha anterior conservada")
        _equal(header["fecha_checkout"],_date("2025-06-02"),"Checkout anterior conservado")
        _equal(fixture.rows("SELECT COUNT(*) n FROM reserva_habitacion WHERE id_reserva=800")[0]["n"],1,"Detalle confirmado")
        return {"header_update":error,"preserved_header":header,"committed_detail":1}

    def overlap_shapes() -> dict:
        fixture.base()
        fixture.reservation(700,"2025-06-10","2025-06-20",1000)
        fixture.reservation(701,"2025-06-01","2025-06-10",900)
        observed=[]
        for index,(start,end,label) in enumerate((("2025-06-19","2025-06-21","parcial"),("2025-06-12","2025-06-13","contenido"),("2025-06-01","2025-07-01","contenedor")),710):
            observed.append(isolated_error(lambda i=index,a=start,b=end:fixture.reservation(i,a,b,100),20304,label))
        return {"contiguous_accepted":True,"rejected":observed}

    def bulk_overlap() -> dict:
        fixture.base()
        for identifier in (700,701):
            fixture.execute("INSERT INTO reserva(id_reserva,id_cliente,id_alojamiento,fecha_checkin,fecha_checkout,valor_total) VALUES(:id,2,1,DATE '2025-06-01',DATE '2025-06-02',100)",{"id":identifier})
        first=_expect_error(lambda:fixture.execute("INSERT INTO reserva_habitacion SELECT 700,1,1,100 FROM dual UNION ALL SELECT 701,1,1,100 FROM dual"),20304,"INSERT multirregistro")
        _equal(fixture.rows("SELECT COUNT(*) n FROM reserva_habitacion")[0]["n"],0,"Rechazo de toda la sentencia INSERT")
        fixture.execute("INSERT INTO reserva_habitacion VALUES(700,1,1,100)")
        fixture.execute("INSERT INTO reserva_habitacion VALUES(701,2,1,100)")
        second=_expect_error(lambda:fixture.execute("UPDATE reserva_habitacion SET id_habitacion=1 WHERE id_reserva IN(700,701)"),20304,"UPDATE multirregistro")
        _equal([r["id_habitacion"] for r in fixture.rows("SELECT id_habitacion FROM reserva_habitacion ORDER BY id_reserva")],[1,2],"UPDATE revertido")
        return {"insert":first,"update":second,"mutating_table_errors":0}

    def header_updates() -> dict:
        fixture.base()
        fixture.reservation(700,"2025-06-01","2025-06-05",400)
        fixture.reservation(701,"2025-06-02","2025-06-04",200,status="CANCELADA")
        reactivate=_expect_error(lambda:fixture.execute("UPDATE reserva SET estado='PENDIENTE' WHERE id_reserva=701"),20304,"Reactivacion solapada")
        _equal(fixture.rows("SELECT estado FROM reserva WHERE id_reserva=701")[0]["estado"],"CANCELADA","Estado anterior")
        fixture.reservation(702,"2025-06-06","2025-06-07",100)
        dates=_expect_error(lambda:fixture.execute("UPDATE reserva SET fecha_checkin=DATE '2025-06-03',fecha_checkout=DATE '2025-06-04' WHERE id_reserva=702"),20304,"Cambio de fechas solapado")
        _equal(fixture.rows("SELECT fecha_checkin FROM reserva WHERE id_reserva=702")[0]["fecha_checkin"],_date("2025-06-06"),"Fechas anteriores")
        return {"reactivation":reactivate,"dates":dates}

    def cancelled_reuse() -> dict:
        fixture.base()
        fixture.reservation(700,"2025-06-01","2025-06-02",100,status="CANCELADA")
        created=fixture.create()
        error=_expect_error(lambda:fixture.create(),20304,"Pendiente bloquea tercera solicitud")
        _equal(fixture.rows("SELECT estado FROM reserva WHERE id_reserva=:id",{"id":created["id_reserva"]})[0]["estado"],"PENDIENTE","Nueva pendiente")
        return {"cancelled_reused":True,"pending":created,"third_request":error}

    def audit_single() -> dict:
        fixture.base()
        start=fixture.rows("SELECT CAST(SYSTIMESTAMP AT TIME ZONE 'UTC' AS TIMESTAMP) n FROM dual")[0]["n"]
        fixture.execute("UPDATE tarifa SET precio_noche=120 WHERE id_tarifa=1")
        end=fixture.rows("SELECT CAST(SYSTIMESTAMP AT TIME ZONE 'UTC' AS TIMESTAMP) n FROM dual")[0]["n"]
        rows=fixture.rows("SELECT id_tarifa,usuario_oracle,fecha_cambio,precio_anterior,precio_nuevo,operacion,id_sentencia FROM auditoria_tarifa")
        _equal(len(rows),1,"Un evento")
        row=rows[0]
        _equal((row["id_tarifa"],row["usuario_oracle"],row["precio_anterior"],row["precio_nuevo"],row["operacion"]),(1,fixture.owner,100,120,"UPDATE"),"Auditoria exacta")
        if not start<=row["fecha_cambio"]<=end:
            raise AssertionError("La fecha de auditoria no corresponde a la ventana UTC del UPDATE.")
        _equal(len(row["id_sentencia"]),16,"Identificador de sentencia RAW(16)")
        return row

    def audit_bulk() -> dict:
        fixture.base()
        for identifier in range(4,101):
            fixture.room(identifier,1)
            fixture.execute("INSERT INTO tarifa(id_tarifa,id_habitacion,id_temporada,precio_noche) VALUES(:id,:id,1,100)",{"id":identifier})
        fixture.execute("UPDATE tarifa SET precio_noche=precio_noche+1")
        rows=fixture.rows("SELECT id_tarifa,usuario_oracle,fecha_cambio,precio_anterior,precio_nuevo,id_sentencia FROM auditoria_tarifa ORDER BY id_tarifa")
        _equal(len(rows),100,"Cien eventos")
        _equal(len({r["id_tarifa"] for r in rows}),100,"Sin IDs duplicados")
        _equal(len({r["id_sentencia"] for r in rows}),1,"Una identidad de sentencia")
        _equal(len({r["fecha_cambio"] for r in rows}),1,"Una marca temporal")
        _equal({(r["precio_anterior"],r["precio_nuevo"],r["usuario_oracle"]) for r in rows},{(100,101,fixture.owner)},"Pares completos")
        return {"events":100,"statement_ids":1,"timestamps":1,"first":rows[0],"last":rows[-1]}

    def audit_no_change() -> dict:
        fixture.base()
        fixture.execute("UPDATE tarifa SET precio_noche=precio_noche")
        fixture.execute("UPDATE tarifa SET precio_noche=120 WHERE id_tarifa=999")
        count=fixture.rows("SELECT COUNT(*) n FROM auditoria_tarifa")[0]["n"]
        _equal(count,0,"No se auditan filas sin cambio")
        return {"events":count}

    def audit_rollback() -> dict:
        fixture.base()
        connection.commit()
        fixture.execute("UPDATE tarifa SET precio_noche=120 WHERE id_tarifa=1")
        _equal(fixture.rows("SELECT COUNT(*) n FROM auditoria_tarifa")[0]["n"],1,"Evento antes del rollback")
        connection.rollback()
        _money(fixture.rows("SELECT precio_noche FROM tarifa WHERE id_tarifa=1")[0]["precio_noche"],100,"Precio revertido")
        _equal(fixture.rows("SELECT COUNT(*) n FROM auditoria_tarifa")[0]["n"],0,"Auditoria revertida")
        return {"price":100,"events":0}

    def audit_failed_statement() -> dict:
        fixture.base()
        before=fixture.rows("SELECT id_tarifa,precio_noche FROM tarifa ORDER BY id_tarifa")
        error=_expect_error(lambda:fixture.execute("UPDATE tarifa SET precio_noche=CASE WHEN id_tarifa=2 THEN -1 ELSE precio_noche+10 END"),2290,"UPDATE masivo invalido")
        _equal(fixture.rows("SELECT id_tarifa,precio_noche FROM tarifa ORDER BY id_tarifa"),before,"Precios previos")
        _equal(fixture.rows("SELECT COUNT(*) n FROM auditoria_tarifa")[0]["n"],0,"Sin auditoria parcial")
        return {"error":error,"events":0,"prices_preserved":True}

    def liquidation_source(two_lodgings: bool = False) -> dict:
        fixture.base(prices={1:200})
        fixture.execute("UPDATE servicio SET precio_unitario=50 WHERE id_servicio=1")
        first=fixture.completed(services=[(1,1)])
        if two_lodgings:
            fixture.completed(rooms=[(3,1)],lodging=2)
        return first

    def liquidation_cut() -> dict:
        liquidation_source()
        january=fixture.liquidate(month=1)
        _equal(january,{"created":0,"preserved":0},"Enero excluido")
        february=fixture.liquidate()
        row=fixture.rows("SELECT * FROM liquidacion_mensual")[0]
        _equal(february,{"created":1,"preserved":0},"Un corte nuevo")
        for key,value in (("total_hospedaje",200),("total_servicios",50),("base_comision",250),("comision_plataforma",30),("neto_propietario",220),("porcentaje_comision",12)):
            _money(row[key],value,key)
        _equal(row["criterio_liquidacion"],COMMISSION_CRITERION,"Criterio capturado")
        return {"january":january,"february":february,"cut":row}

    def excluded_liquidation_states() -> dict:
        fixture.base()
        for day,state in enumerate(("PENDIENTE","CONFIRMADA","CHECKED_IN","CANCELADA"),1):
            created=fixture.create(f"2025-02-{day:02}",f"2025-02-{day+1:02}")
            fixture.execute("UPDATE reserva SET estado=:state WHERE id_reserva=:id",{"state":state,"id":created["id_reserva"]})
        result=fixture.liquidate()
        _equal(result,{"created":0,"preserved":0},"Estados no elegibles excluidos")
        _equal(fixture.rows("SELECT COUNT(*) n FROM liquidacion_mensual")[0]["n"],0,"Sin corte")
        return {"excluded_states":["PENDIENTE","CONFIRMADA","CHECKED_IN","CANCELADA"],"result":result}

    def liquidation_no_product() -> dict:
        fixture.base(prices={2:200})
        fixture.execute("UPDATE servicio SET precio_unitario=CASE id_servicio WHEN 1 THEN 10 WHEN 2 THEN 20 ELSE precio_unitario END")
        fixture.completed(rooms=[(1,1),(2,1)],services=[(1,1),(2,1)])
        fixture.liquidate()
        row=fixture.rows("SELECT total_hospedaje,total_servicios,base_comision,comision_plataforma,neto_propietario FROM liquidacion_mensual")[0]
        for key,value in (("total_hospedaje",300),("total_servicios",30),("base_comision",330),("comision_plataforma",39.6),("neto_propietario",290.4)):
            _money(row[key],value,key)
        return row

    def liquidation_repetition() -> dict:
        source=liquidation_source()
        fixture.liquidate()
        original=fixture.rows("SELECT * FROM liquidacion_mensual")[0]
        repeated=fixture.liquidate()
        _equal(repeated,{"created":0,"preserved":1},"Repeticion identica")
        _equal(fixture.rows("SELECT * FROM liquidacion_mensual")[0],original,"Sin DML en repeticion")
        fixture.execute("SAVEPOINT stable_cut")
        fixture.execute("UPDATE reserva_servicio SET precio_unitario_aplicado=60,subtotal=60 WHERE id_reserva=:id",{"id":source["id_reserva"]})
        fixture.execute("UPDATE reserva SET valor_total=260 WHERE id_reserva=:id",{"id":source["id_reserva"]})
        changed=_expect_error(lambda:fixture.liquidate(),20321,"Fuente monetaria distinta")
        fixture.execute("ROLLBACK TO stable_cut")
        rate=_expect_error(lambda:fixture.liquidate(percentage=11),20321,"Porcentaje distinto")
        fixture.execute("UPDATE reserva SET estado='CANCELADA' WHERE id_reserva=:id",{"id":source["id_reserva"]})
        empty=_expect_error(lambda:fixture.liquidate(),20321,"Fuente ahora vacia")
        fixture.execute("ROLLBACK TO stable_cut")
        states=[]
        for state in ("DISPERSADA","PAGADA"):
            fixture.execute("UPDATE liquidacion_mensual SET estado=:state",{"state":state})
            stable=fixture.rows("SELECT * FROM liquidacion_mensual")[0]
            _equal(fixture.liquidate(),{"created":0,"preserved":1},"Corte cerrado identico conservado")
            states.append(_expect_error(lambda:fixture.liquidate(percentage=11),20322,state))
            _equal(fixture.rows("SELECT * FROM liquidacion_mensual")[0],stable,"Corte cerrado intacto")
        return {"repeated":repeated,"changed_source":changed,"changed_rate":rate,"empty_source":empty,"closed_states":states}

    def concurrent_liquidation() -> dict:
        liquidation_source()
        connection.commit()
        first=fixture.liquidate()
        def run_other(other: Any) -> dict:
            value=fixture.liquidate(connection=other)
            other.commit()
            return value
        second=worker(run_other)
        try:
            second.assert_waiting()
            connection.commit()
            result=second.finish()
        finally:
            connection.rollback()
        _equal(first,{"created":1,"preserved":0},"Primer corte")
        _equal(result,{"created":0,"preserved":1},"Segundo corte conserva")
        _equal(fixture.rows("SELECT COUNT(*) n FROM liquidacion_mensual")[0]["n"],1,"Un solo corte persistido")
        return {"first":first,"second":result,"persisted":1}

    def liquidation_partial_rollback() -> dict:
        liquidation_source(two_lodgings=True)
        fixture.temporary_trigger("TRG_E2_TEST_LIQUIDACION_FAIL", """BEFORE INSERT ON liquidacion_mensual FOR EACH ROW
            BEGIN IF :NEW.id_alojamiento=2 THEN RAISE_APPLICATION_ERROR(-20992,'Fallo controlado segundo alojamiento'); END IF; END;""")
        fixture.execute("INSERT INTO municipio(id_municipio,nombre) VALUES(901,'Marcador previo L06')")
        error=_expect_error(lambda:fixture.liquidate(),20992,"Fallo en segundo alojamiento del lote")
        _equal(fixture.rows("SELECT COUNT(*) n FROM liquidacion_mensual")[0]["n"],0,"Ningun corte parcial")
        _equal(fixture.rows("SELECT COUNT(*) n FROM municipio WHERE id_municipio=901")[0]["n"],1,"Trabajo previo conservado")
        other=owner_connection()
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM municipio WHERE id_municipio=901")
                _equal(cursor.fetchone()[0],0,"Trabajo previo no confirmado")
        finally:
            other.close()
        return {"error":error,"partial_cuts":0,"prior_work_preserved":True,"prior_work_committed":False}

    def liquidation_invalid_inputs() -> dict:
        fixture.base()
        _equal(fixture.liquidate(),{"created":0,"preserved":0},"Mes sin actividad")
        observed=[]
        for percentage in (None,-1,101,12.34567):
            observed.append(_expect_error(lambda p=percentage:fixture.liquidate(percentage=p),20320,f"Porcentaje {percentage}"))
        for year,month in ((2025,0),(2025,13),(2025,None),(2025.5,2),(None,2),(9999,12)):
            observed.append(_expect_error(lambda y=year,m=month:fixture.liquidate(year=y,month=m),20320,f"Periodo {year}/{month}"))
        _equal(fixture.rows("SELECT COUNT(*) n FROM liquidacion_mensual")[0]["n"],0,"Entradas invalidas sin cortes")
        return {"empty_month_created":0,"rejected":observed}

    def liquidation_legacy() -> dict:
        liquidation_source()
        fixture.execute("INSERT INTO liquidacion_mensual(id_alojamiento,periodo_anio,periodo_mes,total_hospedaje,total_servicios,comision_plataforma,neto_propietario) VALUES(1,2025,2,200,50,30,220)")
        error=_expect_error(lambda:fixture.liquidate(),20323,"Corte legado sin politica")
        fixture.execute("DELETE FROM liquidacion_mensual")
        fixture.execute("UPDATE tarifa SET precio_noche=900 WHERE id_habitacion=1")
        fixture.liquidate()
        row=fixture.rows("SELECT total_hospedaje,total_servicios,base_comision,comision_plataforma,neto_propietario FROM liquidacion_mensual")[0]
        _money(row["total_hospedaje"],200,"Se liquida hospedaje contratado")
        _money(row["neto_propietario"],220,"Catalogo actual no altera corte")
        return {"legacy_rejection":error,"cut_from_stored_contract":row}

    def installation() -> dict:
        installed=fixture.rows("SELECT object_name,object_type,status FROM user_objects WHERE object_name IN ('PKG_TURISMOUQ','TRG_AUDITAR_TARIFA','TRG_RESERVA_HABITACION','TRG_RESERVA') ORDER BY object_name,object_type")
        _equal({(r["object_name"],r["object_type"]) for r in installed},PRODUCTION_OBJECTS,"Objetos PL/SQL completos")
        _equal({r["status"] for r in installed},{"VALID"},"Objetos validos")
        errors=fixture.rows("SELECT name,type,line,position,text FROM user_errors WHERE name IN ('PKG_TURISMOUQ','TRG_AUDITAR_TARIFA','TRG_RESERVA_HABITACION','TRG_RESERVA') AND attribute='ERROR'")
        _equal(errors,[],"Sin errores de compilacion")
        triggers=fixture.rows("SELECT trigger_name,status,trigger_type FROM user_triggers WHERE trigger_name IN ('TRG_AUDITAR_TARIFA','TRG_RESERVA_HABITACION','TRG_RESERVA') ORDER BY trigger_name")
        _equal(len(triggers),3,"Tres triggers")
        _equal({r["status"] for r in triggers},{"ENABLED"},"Triggers habilitados")
        _equal({r["trigger_type"] for r in triggers},{"COMPOUND"},"Fases compuestas instaladas")
        repeated=external("I01")
        if not isinstance(repeated,dict) or repeated.get("installation_runs",0)<2:
            raise AssertionError("Falta evidencia de dos instalaciones compatibles en el esquema de prueba.")
        return {"objects":installed,"triggers":triggers,"compile_errors":errors,"repeated_installation":repeated}

    def runtime_permissions() -> dict:
        if runtime_connection_factory is None:
            raise AssertionError("I02 requiere runtime_connection_factory; no se omite la prueba de permisos.")
        fixture.base()
        connection.commit()
        runtime=runtime_connection_factory()
        try:
            runtime.autocommit=False
            with runtime.cursor() as cursor:
                cursor.execute("SELECT USER FROM dual")
                runtime_user=cursor.fetchone()[0]
            if runtime_user==fixture.owner:
                raise AssertionError("El usuario de ejecucion debe ser distinto del propietario.")
            def direct_write() -> None:
                with runtime.cursor() as cursor:
                    cursor.execute(f'INSERT INTO "{fixture.owner}".municipio(id_municipio,nombre) VALUES(999,\'DML prohibido\')')
            rejected=_expect_error(direct_write,{1031,942},"DML directo denegado")
            runtime.rollback()
            created=fixture.create(connection=runtime)
            runtime.commit()
            _money(created["valor_total"],100,"Reserva autorizada por paquete")
            _equal(fixture.rows("SELECT COUNT(*) n FROM reserva WHERE id_reserva=:id",{"id":created["id_reserva"]})[0]["n"],1,"Reserva persistida por runtime")
            _equal(fixture.rows("SELECT COUNT(*) n FROM municipio WHERE id_municipio=999")[0]["n"],0,"Sin DML prohibido")
            return {"runtime_user":runtime_user,"direct_dml":rejected,"package_reservation":created}
        finally:
            runtime.rollback()
            runtime.close()

    def regression_integration() -> dict:
        regression=external("I03")
        cancellation=cancelled_reuse()
        return {"e1_regression":regression,"operational_cancellation":cancellation}

    cases: list[tuple[str,Any,Callable[[],Any]]] = [
        ("F01",{"amount":300,"written_rows":0},lambda:basic_quote("2025-06-01","2025-06-04",300)),
        ("F02",{"amount":500,"segment_nights":[2,2]},crossing),
        ("F03",{"amount":100},excluded_checkout),
        ("F04",{"nights":367,"amount":3670},lambda:basic_quote("2024-01-01","2025-01-02",3670,10)),
        ("F05",{"invalid_dates_rejected":True,"written_rows":0},invalid_dates),
        ("F06",{"coverage_anomalies_rejected":5},coverage_errors),
        ("F07",{"historical":500,"new_quote":540},historical_price),
        ("F08",{"oracle_code":20311,"partial_rows":0},monetary_overflow),
        ("R01",{"room_amounts":[400,600],"services":[60,40],"total":1100},reservation_totals),
        ("R02",{"exact_capacity_accepted":True,"invalid_people_quantities_rejected":True},capacity),
        ("R03",{"invalid_references_and_operational_states_rejected":True,"date_error_before_overlap":True},invalid_references),
        ("R04",{"error":20991,"partial_rows":0,"prior_work_preserved":True},reservation_partial_rollback),
        ("R05",{"remaining_contract_rows":0},reservation_caller_rollback),
        ("C01",{"persisted":1,"second_error":20304},lambda:concurrent_reservation(True)),
        ("C02",{"persisted":1,"second_accepted_after_rollback":True},lambda:concurrent_reservation(False)),
        ("C03",{"oracle_code":20312,"partial_rows":0},lock_timeout),
        ("C04",{"independent_room_accepted":True,"reverse_order_deadlocks":0},independent_and_reversed),
        ("C05",{"captured_price":100,"new_quote":480,"barrier_observed":True},concurrent_price_capture),
        ("C06",{"header_update_error":20304,"committed_detail":1,"header_preserved":True},concurrent_header_detail),
        ("T01",{"contiguous_accepted":True,"overlap_shapes_rejected":3},overlap_shapes),
        ("T02",{"insert_update_statements_rejected":True,"mutating_table_errors":0},bulk_overlap),
        ("T03",{"invalid_reactivation_dates_rejected":True},header_updates),
        ("T04",{"cancelled_reused":True,"pending_blocks_third":True},cancelled_reuse),
        ("A01",{"actor":"SESSION_USER","before":100,"after":120,"time":"UTC","statement_raw_bytes":16},audit_single),
        ("A02",{"events":100,"statement_ids":1},audit_bulk),
        ("A03",{"events":0},audit_no_change),
        ("A04",{"price":100,"events":0},audit_rollback),
        ("A05",{"oracle_code":2290,"events":0,"prices_preserved":True},audit_failed_statement),
        ("L01",{"january_created":0,"base":250,"commission":30,"net":220},liquidation_cut),
        ("L02",{"ineligible_states_excluded":4,"created":0},excluded_liquidation_states),
        ("L03",{"base":330,"commission":39.6,"net":290.4},liquidation_no_product),
        ("L04",{"identical_preserved":True,"changed_or_empty_source_rejected":True,"closed_cuts_preserved":True},liquidation_repetition),
        ("L05",{"persisted":1,"second_preserved":1},concurrent_liquidation),
        ("L06",{"error":20992,"partial_cuts":0,"prior_work_preserved":True},liquidation_partial_rollback),
        ("L07",{"empty_month_created":0,"invalid_parameters_rejected":True},liquidation_invalid_inputs),
        ("L08",{"legacy_error":20323,"contract_amount_preserved":200},liquidation_legacy),
        ("I01",{"production_objects_valid":5,"triggers_enabled":3,"installation_runs":2},installation),
        ("I02",{"direct_dml_denied":True,"package_execution_accepted":True},runtime_permissions),
        ("I03",{"e1_regression_passed":True,"cancelled_reuse_accepted":True},regression_integration),
        ("I04",{"original_schemas_preserved":True},lambda:external("I04")),
    ]
    _equal(tuple(item[0] for item in cases),CASE_IDS,"Matriz completa de 40 IDs unicos")
    try:
        for identifier,expected,action in cases:
            record: dict[str,Any]={"id":identifier,"status":"RUNNING","expected":expected}
            results.append(record)
            persist()
            try:
                fixture.guard()
                record["observed"]=action()
                record["status"]="PASS"
            except Exception as error:
                record["status"]="FAIL"
                record["observed"]={"error":str(error),"oracle_code":_oracle_code(error)}
            finally:
                try:
                    connection.rollback()
                    for current_worker in workers:
                        if not current_worker.finished.is_set():
                            try:
                                current_worker.finish()
                            except Exception as error:
                                if not current_worker.finished.is_set():
                                    raise RuntimeError("No es seguro limpiar mientras una segunda sesion sigue activa.") from error
                    workers.clear()
                    record["cleanup"]=fixture.cleanup()
                except Exception as error:
                    record["status"]="FAIL"
                    record["cleanup_error"]=str(error)
                persist()
    finally:
        connection.rollback()
        try:
            fixture.cleanup()
        finally:
            connection.autocommit=previous_autocommit
            persist()
    return results
