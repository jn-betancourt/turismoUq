"""Valida atomicidad, concurrencia y permisos en un esquema E3 aislado de Oracle XE."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from getpass import getpass
import os
from pathlib import Path
import secrets
import shutil
from threading import Event
from time import perf_counter
from uuid import uuid4

import oracledb

from validar_local import ROOT, checked_identifier, write_json


ROLE_SUFFIXES = ("RECEPCION", "ADMIN_ALOJAMIENTO", "GERENTE", "AUDITOR")
START = date(2027, 1, 9)
SECOND_START = date(2027, 1, 11)
RACE_START = date(2027, 1, 13)
OWNER_CALL = """
DECLARE
    rooms pkg_turismouq.lista_solicitudes_habitacion := pkg_turismouq.lista_solicitudes_habitacion();
    services pkg_turismouq.lista_solicitudes_servicio := pkg_turismouq.lista_solicitudes_servicio();
BEGIN
    rooms.EXTEND;
    rooms(1).id_habitacion := :room;
    rooms(1).personas_hospedadas := 1;
    sp_reserva_con_pago(:customer, :lodging, :arrival, :departure, rooms, services,
                        :amount, 'EFECTIVO', :reservation, :payment, :total);
END;"""


def connect(account, password, service):
    connection = oracledb.connect(user=account, password=password, dsn=service)
    connection.call_timeout = 15_000
    with connection.cursor() as cursor:
        cursor.execute("ALTER SESSION SET NLS_CALENDAR='GREGORIAN'")
        cursor.execute("ALTER SESSION SET ISOLATION_LEVEL=READ COMMITTED")
    return connection


def scalar(cursor, sql, **binds):
    cursor.execute(sql, binds)
    return cursor.fetchone()[0]


def expect_error(action, *expected):
    try:
        action()
    except oracledb.DatabaseError as error:
        code = error.args[0].code
        if code in expected:
            return code
        raise
    raise AssertionError(f"Oracle debía rechazar la operación con {expected}.")


def fixture(cursor):
    cursor.execute(
        """SELECT h.id_habitacion, h.id_alojamiento FROM v_e3_habitaciones h
           WHERE NOT EXISTS (
               SELECT 1 FROM reserva_habitacion rh JOIN reserva r ON r.id_reserva = rh.id_reserva
               WHERE rh.id_habitacion = h.id_habitacion AND r.estado <> 'CANCELADA'
                 AND r.fecha_checkin < DATE '2027-01-15' AND r.fecha_checkout > DATE '2027-01-09'
           ) ORDER BY h.id_habitacion FETCH FIRST 1 ROW ONLY"""
    )
    room, lodging = cursor.fetchone()
    customer = scalar(cursor, "SELECT MIN(id_cliente) FROM v_e3_clientes")
    return {"room": room, "lodging": lodging, "customer": customer}


def quote(cursor, room, start):
    return scalar(
        cursor, "SELECT pkg_turismouq.fn_valor_estadia(:room, :start_day, :end_day) FROM dual",
        room=room, start_day=start, end_day=start + timedelta(days=1),
    )


def owner_booking(cursor, data, start, amount):
    reservation, payment, total = (cursor.var(int), cursor.var(int), cursor.var(float))
    cursor.execute(OWNER_CALL, data | {
        "arrival": start, "departure": start + timedelta(days=1), "amount": amount,
        "reservation": reservation, "payment": payment, "total": total,
    })
    return int(reservation.getvalue()), int(payment.getvalue()), total.getvalue()


def view_booking(cursor, schema, data, start, amount, token=None):
    token = token or uuid4().hex
    cursor.execute(
        f"""INSERT INTO {schema}.v_e3_solicitud_pago (
               token_solicitud, id_cliente, id_alojamiento, fecha_checkin, fecha_checkout,
               id_habitacion, personas, monto, metodo_pago)
            VALUES (HEXTORAW(:token), :customer, :lodging, :arrival, :departure, :room, 1, :amount, 'EFECTIVO')""",
        data | {"token": token, "amount": amount, "arrival": start, "departure": start + timedelta(days=1)},
    )
    return token


def get_receipt(cursor, schema, token):
    cursor.execute(
        f"""SELECT id_reserva, id_pago, monto, estado_reserva
           FROM {schema}.v_e3_solicitud_pago WHERE token_solicitud=HEXTORAW(:token)""",
        token=token,
    )
    return cursor.fetchone()


def atomicity(owner, data):
    with owner.cursor() as cursor:
        amount = quote(cursor, data["room"], START)
        reservation, payment, total = owner_booking(cursor, data, START, amount)
        assert total == amount
        # Catch inside the same anonymous statement to ensure Oracle's automatic
        # statement rollback cannot conceal a missing ROLLBACK TO SAVEPOINT.
        failed_amount = quote(cursor, data["room"], SECOND_START) + 1
        assert failed_amount > 0
        error_code = cursor.var(int)
        nested_call = OWNER_CALL.strip().removesuffix("END;") + """
        EXCEPTION
            WHEN OTHERS THEN :error_code := SQLCODE;
        END;"""
        cursor.execute(nested_call, data | {
            "arrival": SECOND_START, "departure": SECOND_START + timedelta(days=1), "amount": failed_amount,
            "reservation": cursor.var(int), "payment": cursor.var(int), "total": cursor.var(float),
            "error_code": error_code,
        })
        assert error_code.getvalue() == -20401
        assert scalar(cursor, """SELECT COUNT(*) FROM reserva r
            WHERE r.id_cliente=:customer AND r.id_alojamiento=:lodging AND r.fecha_checkin=:arrival""",
            customer=data["customer"], lodging=data["lodging"], arrival=SECOND_START) == 0
        cursor.execute(
            """SELECT r.estado, p.estado_pago, p.monto FROM reserva r JOIN pago p ON p.id_reserva=r.id_reserva
               WHERE r.id_reserva=:reservation AND p.id_pago=:payment""",
            reservation=reservation, payment=payment,
        )
        assert cursor.fetchone() == ("CONFIRMADA", "APROBADO", amount)
    owner.rollback()
    with owner.cursor() as cursor:
        assert scalar(cursor, "SELECT COUNT(*) FROM reserva WHERE id_reserva=:res", res=reservation) == 0
        assert scalar(cursor, "SELECT COUNT(*) FROM pago WHERE id_pago=:pay", pay=payment) == 0
    return {"error_pago": -20401, "trabajo_previo_conservado": True, "rollback_final_demostracion": True}


def check_roles(admin, owner, open_account, schema, data):
    with owner.cursor() as cursor:
        amount = quote(cursor, data["room"], START)
    with open_account("RECEPCION") as reception, reception.cursor() as cursor:
        for table in ("RESERVA", "PAGO", "CLIENTE", "USUARIO_SISTEMA", "SOLICITUD_PAGO"):
            expect_error(lambda: cursor.execute(f"SELECT * FROM {schema}.{table}"), 942, 1031)
        expect_error(lambda: cursor.execute(f"UPDATE {schema}.pago SET monto=1"), 942, 1031)
        expect_error(lambda: cursor.execute(f"SELECT * FROM {schema}.v_e3_auditoria_tarifa"), 942, 1031)
        expect_error(lambda: cursor.execute(f"SELECT {schema}.pkg_turismouq.fn_valor_estadia(1, SYSDATE, SYSDATE+1) FROM dual"), 904, 6550)
        assert scalar(cursor, f"SELECT COUNT(*) FROM {schema}.v_e3_alojamientos") > 0
        assert expect_error(lambda: view_booking(cursor, schema, data, START, amount + 1), 20401) == 20401
        assert scalar(cursor, f"SELECT COUNT(*) FROM {schema}.v_e3_solicitud_pago") == 0
        token = view_booking(cursor, schema, data, START, amount)
        assert get_receipt(cursor, schema, token)[2:] == (amount, "CONFIRMADA")
        reception.rollback()
        assert get_receipt(cursor, schema, token) is None

    with open_account("ADMIN_ALOJAMIENTO") as accommodation, accommodation.cursor() as cursor:
        tariff = scalar(cursor, f"SELECT MIN(id_tarifa) FROM {schema}.v_e3_admin_tarifas")
        cursor.execute(f"UPDATE {schema}.v_e3_admin_tarifas SET precio_noche=precio_noche+1 WHERE id_tarifa=:tariff", tariff=tariff)
        assert cursor.rowcount == 1
        expect_error(lambda: cursor.execute(f"UPDATE {schema}.v_e3_admin_tarifas SET id_temporada=1"), 1031)
        expect_error(lambda: cursor.execute(f"SELECT * FROM {schema}.reserva"), 942, 1031)
        accommodation.rollback()

    with open_account("GERENTE") as manager, manager.cursor() as cursor:
        assert scalar(cursor, f"SELECT COUNT(*) FROM {schema}.v_e3_gerencia_mensual") > 0
        expect_error(lambda: cursor.execute(f"UPDATE {schema}.v_e3_admin_tarifas SET precio_noche=1"), 942, 1031)

    with open_account("AUDITOR") as auditor, auditor.cursor() as cursor:
        scalar(cursor, f"SELECT COUNT(*) FROM {schema}.v_e3_auditoria_tarifa")
        expect_error(lambda: cursor.execute(f"DELETE FROM {schema}.v_e3_auditoria_tarifa"), 942, 1031)
        expect_error(lambda: cursor.execute(f"SELECT * FROM {schema}.v_e3_clientes"), 942, 1031)

    with open_account("RECEPCION"), open_account("RECEPCION"), open_account("RECEPCION"):
        expect_error(lambda: open_account("RECEPCION").close(), 2391)
    with admin.cursor() as cursor:
        cursor.execute(
            """SELECT resource_name, limit FROM dba_profiles
               WHERE profile=:profile AND resource_name IN ('SESSIONS_PER_USER', 'CONNECT_TIME', 'IDLE_TIME')
               ORDER BY resource_name""", profile=f"{schema}_PERFIL",
        )
        limits = dict(cursor)
        assert limits == {"CONNECT_TIME": "240", "IDLE_TIME": "15", "SESSIONS_PER_USER": "3"}
        cursor.execute("SELECT DISTINCT role, table_name, privilege FROM role_tab_privs WHERE role LIKE :prefix",
                       prefix=f"{schema}%")
        grants = [list(row) for row in cursor if row[0] in {f"{schema}_{role}" for role in ROLE_SUFFIXES}]
        assert grants and all(view.startswith("V_E3_") for _, view, _ in grants)
    return {"roles_verificados": list(ROLE_SUFFIXES), "limites": limits, "ora_cuarta_sesion": 2391,
            "recepcion_solo_vistas": True, "grants_objetos": sorted(grants)}


def concurrent_bookings(admin, owner, open_account, schema, data):
    control_table = "E3_CONTROL_" + secrets.token_hex(4).upper()
    with owner.cursor() as first, owner.cursor() as inspector:
        first.execute(f"CREATE TABLE {control_table} (id NUMBER PRIMARY KEY, habitacion NUMBER, entrada DATE, salida DATE)")
        try:
            # The second transaction checks the same room before any lock is taken.
            # It needs owner rights only for this throwaway table, never for the real scenario.
            with open_account("OWNER") as second, second.cursor() as other:
                window = {"room": data["room"], "arrival": RACE_START, "departure": RACE_START + timedelta(days=1)}
                available = (f"SELECT COUNT(*) FROM {control_table} "
                             "WHERE habitacion=:room AND entrada<:departure AND salida>:arrival")
                assert scalar(first, available, **window) == scalar(other, available, **window) == 0
                insert = f"INSERT INTO {control_table} VALUES (:request_id, :room, :arrival, :departure)"
                first.execute(insert, request_id=1, **window)
                started = perf_counter()
                other.execute(insert, request_id=2, **window)
                baseline_ms = round((perf_counter() - started) * 1000, 3)
                second.commit()
                owner.commit()
                assert scalar(inspector, f"SELECT COUNT(*) FROM {control_table}") == 2
        finally:
            owner.rollback()
            first.execute(f"DROP TABLE {control_table} PURGE")

        amount = quote(first, data["room"], RACE_START)

    with open_account("RECEPCION") as session_a, open_account("SECOND_RECEPTION") as session_b,          session_a.cursor() as first, session_b.cursor() as second, admin.cursor() as monitor:
        sid_a = int(scalar(first, "SELECT SYS_CONTEXT('USERENV', 'SID') FROM dual"))
        sid_b = int(scalar(second, "SELECT SYS_CONTEXT('USERENV', 'SID') FROM dual"))
        token = view_booking(first, schema, data, RACE_START, amount)
        reservation, payment, _, _ = get_receipt(first, schema, token)
        assert get_receipt(second, schema, token) is None
        waiter_started = Event()

        def try_second_booking():
            with session_b.cursor() as cursor:
                start = perf_counter()
                waiter_started.set()
                code = expect_error(lambda: view_booking(cursor, schema, data, RACE_START, amount), 20304, 20312)
                session_b.rollback()
                return code, round((perf_counter() - start) * 1000, 3)

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(try_second_booking)
                assert waiter_started.wait(2)
                blocking = None
                deadline = perf_counter() + 3
                try:
                    while perf_counter() < deadline:
                        monitor.execute(
                            "SELECT event, blocking_session FROM v$session WHERE sid=:sid AND state='WAITING'",
                            sid=sid_b,
                        )
                        observation = monitor.fetchone()
                        if observation and observation[1] == sid_a and "row lock" in observation[0]:
                            blocking = observation
                            break
                        Event().wait(0.025)
                finally:
                    session_a.commit()
                code, elapsed_ms = result.result(timeout=6)
            assert blocking is not None, "No se observó el bloqueo Oracle entre las dos sesiones."
            assert code == 20304, f"Se esperaba no disponibilidad tras el COMMIT de A: {code}"
            assert get_receipt(second, schema, token) is None  # even after the commit: different principal
            assert get_receipt(first, schema, token)[:2] == (reservation, payment)
            with owner.cursor() as cursor:
                assert scalar(cursor, "SELECT COUNT(*) FROM pago WHERE id_reserva=:res", res=reservation) == 1
                assert scalar(cursor, """SELECT COUNT(*) FROM reserva r
                        JOIN reserva_habitacion rh ON r.id_reserva=rh.id_reserva
                        WHERE rh.id_habitacion=:room AND r.fecha_checkin=:start_day""",
                        room=data["room"], start_day=RACE_START) == 1
        finally:
            session_a.rollback()
            session_b.rollback()
            with owner.cursor() as cursor:
                cursor.execute("DELETE FROM solicitud_pago WHERE id_pago=:identifier", identifier=payment)
                cursor.execute("DELETE FROM pago WHERE id_pago=:identifier", identifier=payment)
                cursor.execute("DELETE FROM reserva WHERE id_reserva=:identifier", identifier=reservation)
            owner.commit()

    return {"sin_bloqueo": {"reservas_solapadas": 2, "insercion_b_ms": baseline_ms},
            "con_for_update": {"sid_a": sid_a, "sid_b": sid_b, "evento_oracle": blocking[0],
                               "sesion_bloqueante": blocking[1], "rechazo_b": code,
                               "espera_b_ms": elapsed_ms, "reservas_confirmadas": 1, "pagos": 1,
                               "comprobante_visible_solo_para_el_emisor": True}}


def run_validation(admin, owner, schema, service, owner_password, evidence):
    suffix = secrets.token_hex(4).upper()
    names = {role: f"UQ3_{suffix}_{i}" for i, role in enumerate((*ROLE_SUFFIXES, "SECOND_RECEPTION"), 1)}
    passwords = {role: "Uq" + secrets.token_hex(12) for role in names}
    accounts_created = []

    def open_account(role):
        if role == "OWNER":
            return connect(schema, owner_password, service)
        return connect(names[role], passwords[role], service)

    with admin.cursor() as cursor:
        try:
            for role, username in names.items():
                cursor.execute(
                    f'CREATE USER {username} IDENTIFIED BY "{passwords[role]}" PROFILE {schema}_PERFIL'
                )
                accounts_created.append(username)
                database_role = "RECEPCION" if role == "SECOND_RECEPTION" else role
                cursor.execute(f"GRANT CREATE SESSION, {schema}_{database_role} TO {username}")

            with owner.cursor() as fixture_cursor:
                data = fixture(fixture_cursor)
            report = {
                "oracle": owner.version,
                "esquema": schema,
                "fixture": data,
                "atomicidad": atomicity(owner, data),
                "seguridad": check_roles(admin, owner, open_account, schema, data),
                "concurrencia": concurrent_bookings(admin, owner, open_account, schema, data),
            }
            write_json(evidence / "validacion.json", report)
            return report
        finally:
            for username in reversed(accounts_created):
                cursor.execute(f"DROP USER {username}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="TURISMOUQ_E3")
    parser.add_argument("--service", default="localhost:1521/xepdb1")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    schema = checked_identifier(options.schema.upper())
    if not schema.startswith("TURISMOUQ_E3"):
        raise ValueError("La validación requiere un esquema separado de Entrega 3.")
    password = os.environ.get("TURISMOUQ_E3_TEST_PASSWORD") or getpass(f"Contraseña de {schema}: ")
    sqlplus = shutil.which("sqlplus")
    if not sqlplus:
        raise RuntimeError("SQL*Plus debe estar en PATH.")
    oracledb.init_oracle_client(lib_dir=str(Path(sqlplus).parent))
    options.output.mkdir(parents=True, exist_ok=True)
    with oracledb.connect(externalauth=True, mode=oracledb.AUTH_MODE_SYSDBA) as admin,          connect(schema, password, options.service) as owner:
        admin.cursor().execute("ALTER SESSION SET CONTAINER=XEPDB1")
        run_validation(admin, owner, schema, options.service, password, options.output)
    print(f"Atomicidad, concurrencia y seguridad aprobadas: {options.output / 'validacion.json'}.")


if __name__ == "__main__":
    main()
