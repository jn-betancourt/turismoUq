"""Operaciones de Entrega 3 a través de las vistas Oracle del propietario."""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import re
from uuid import UUID

import oracledb
import pandas as pd

from app.core.connection import DatabaseConnectionManager


VIEWS = {
    "lodgings": "V_E3_ALOJAMIENTOS",
    "rooms": "V_E3_HABITACIONES",
    "customers": "V_E3_CLIENTES",
    "rates": "V_E3_TARIFAS_COTIZACION",
    "receipts": "V_E3_SOLICITUD_PAGO",
    "administration": "V_E3_ADMIN_TARIFAS",
    "management": "V_E3_GERENCIA_MENSUAL",
    "audit": "V_E3_AUDITORIA_TARIFA",
}
PAYMENT_METHODS = {
    "Efectivo": "EFECTIVO",
    "Transferencia": "TRANSFERENCIA",
    "PSE": "PSE",
    "Tarjeta débito": "TARJETA_DEBITO",
    "Tarjeta crédito": "TARJETA_CREDITO",
}


def normalize_owner(owner: str) -> str:
    owner = owner.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,29}", owner):
        raise ValueError("Indica un propietario Oracle válido, sin comillas.")
    return owner


@dataclass(frozen=True)
class BookingPaymentRequest:
    token: UUID
    customer_id: int
    lodging_id: int
    room_id: int
    check_in: date
    check_out: date
    guests: int
    amount: Decimal
    payment_method: str


@dataclass(frozen=True)
class BookingPaymentReceipt:
    reservation_id: int
    payment_id: int
    amount: Decimal
    status: str


class Entrega3Service:
    def __init__(self, database: DatabaseConnectionManager, owner: str):
        self.database = database
        self.owner = normalize_owner(owner)

    def view(self, name: str) -> str:
        return f"{self.owner}.{VIEWS[name]}"

    def access(self) -> dict:
        """Determina los módulos visibles. Oracle comprueba los permisos en cada consulta."""
        with self.database.get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT view_name FROM all_views WHERE owner = :owner AND view_name LIKE 'V_E3_%'",
                owner=self.owner,
            )
            views = {name for (name,) in cursor}
            cursor.execute("SELECT role FROM session_roles")
            roles = {role for (role,) in cursor}
            is_owner = connection.username.upper() == self.owner
        return {
            "booking": VIEWS["receipts"] in views and (is_owner or f"{self.owner}_RECEPCION" in roles),
            "administration": VIEWS["administration"] in views,
            "management": VIEWS["management"] in views,
            "audit": VIEWS["audit"] in views,
            "legacy": is_owner,
            "roles": sorted(role for role in roles if role.startswith(f"{self.owner}_")),
        }

    def rows(self, sql: str, **binds) -> pd.DataFrame:
        with self.database.get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(sql, binds)
            return pd.DataFrame(cursor.fetchall(), columns=[column.name.lower() for column in cursor.description])

    def lodgings(self) -> pd.DataFrame:
        return self.rows(f"SELECT * FROM {self.view('lodgings')} ORDER BY municipio, nombre")

    def rooms(self, lodging_id: int) -> pd.DataFrame:
        return self.rows(
            f"SELECT * FROM {self.view('rooms')} WHERE id_alojamiento = :lodging ORDER BY numero_habitacion",
            lodging=lodging_id,
        )

    def find_customer(self, document: str) -> pd.DataFrame:
        return self.rows(
            f"SELECT id_cliente, nombre_completo FROM {self.view('customers')} WHERE numero_documento = :document",
            document=document,
        )

    def quote(self, room_id: int, check_in: date, check_out: date) -> Decimal:
        if check_out <= check_in:
            raise ValueError("La salida debe ser posterior a la entrada.")
        current_day = check_in
        amount = Decimal(0)
        with self.database.get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT fecha_inicio, fecha_fin, precio_noche
                FROM {self.view('rates')}
                WHERE id_habitacion = :room AND fecha_inicio < :check_out AND fecha_fin >= :check_in
                ORDER BY fecha_inicio""",
                room=room_id, check_in=check_in, check_out=check_out,
                fetch_decimals=True,
            )
            for start, end, price in cursor:
                start_day = max(start.date(), check_in)
                last_day = min(end.date(), check_out - timedelta(days=1))
                if start_day != current_day or last_day < start_day:
                    raise ValueError("El rango no tiene una tarifa única para cada noche.")
                nights = (last_day - start_day).days + 1
                amount += price * nights
                current_day = last_day + timedelta(days=1)
        if current_day != check_out:
            raise ValueError("Falta una tarifa para una o más noches del rango.")
        return amount

    def receipt(self, cursor: oracledb.Cursor, token: UUID) -> BookingPaymentReceipt | None:
        cursor.execute(
            f"""SELECT id_reserva, id_pago, monto, estado_reserva FROM {self.view('receipts')}
                WHERE token_solicitud = HEXTORAW(:token)""",
            token=token.hex, fetch_decimals=True,
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return BookingPaymentReceipt(int(row[0]), int(row[1]), row[2], row[3])

    def book_and_pay(self, request: BookingPaymentRequest, *, commit: bool) -> BookingPaymentReceipt:
        with self.database.get_connection() as connection, connection.cursor() as cursor:
            existing = self.receipt(cursor, request.token)
            if existing:
                return existing
            try:
                cursor.execute(
                    f"""INSERT INTO {self.view('receipts')} (
                        token_solicitud, id_cliente, id_alojamiento, fecha_checkin, fecha_checkout,
                        id_habitacion, personas, monto, metodo_pago
                    ) VALUES (HEXTORAW(:token), :customer, :lodging, :check_in, :check_out,
                              :room, :guests, :amount, :payment_method)""",
                    token=request.token.hex, customer=request.customer_id, lodging=request.lodging_id,
                    check_in=request.check_in, check_out=request.check_out, room=request.room_id,
                    guests=request.guests, amount=request.amount, payment_method=request.payment_method,
                )
            except oracledb.DatabaseError:
                connection.rollback()
                existing = self.receipt(cursor, request.token)
                if existing:
                    return existing
                raise
            receipt = self.receipt(cursor, request.token)
            if receipt is None:
                raise RuntimeError("Oracle no devolvió el comprobante; se revirtió la operación.")
            if commit:
                connection.commit()
            else:
                connection.rollback()
            return receipt

    def recent_receipts(self) -> pd.DataFrame:
        return self.rows(
            f"""SELECT id_reserva, id_pago, fecha_checkin, fecha_checkout, monto, metodo_pago, estado_reserva
                FROM {self.view('receipts')} ORDER BY fecha_pago DESC, id_pago DESC FETCH FIRST 20 ROWS ONLY"""
        )

    def tariffs(self, room_id: int) -> pd.DataFrame:
        return self.rows(
            f"""SELECT id_tarifa, id_temporada, precio_noche FROM {self.view('administration')}
                WHERE id_habitacion = :room ORDER BY id_temporada""",
            room=room_id,
        )

    def update_tariff(self, tariff_id: int, previous: Decimal, price: Decimal) -> bool:
        with self.database.get_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE {self.view('administration')} SET precio_noche = :price
                    WHERE id_tarifa = :tariff AND precio_noche = :previous""",
                tariff=tariff_id, previous=previous, price=price,
            )
            if cursor.rowcount != 1:
                return False
            connection.commit()
            return True

    def monthly_report(self, month: date) -> pd.DataFrame:
        return self.rows(
            f"""SELECT alojamiento, reservas, valor_contratado FROM {self.view('management')}
                WHERE mes = :month ORDER BY valor_contratado DESC, id_alojamiento""",
            month=month.replace(day=1),
        )

    def audit_report(self) -> pd.DataFrame:
        return self.rows(
            f"""SELECT fecha_cambio, usuario_oracle, id_tarifa, precio_anterior, precio_nuevo, operacion
                FROM {self.view('audit')} ORDER BY fecha_cambio DESC, id_auditoria DESC FETCH FIRST 100 ROWS ONLY"""
        )
