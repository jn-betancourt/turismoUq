"""Servicio de abstraccion para la capa PL/SQL (PKG_TURISMOUQ y Triggers)."""
import datetime as dt
from typing import Dict, Any, List, Tuple, Optional
import oracledb
import pandas as pd
from app.core.connection import db_manager

ERROR_MESSAGES = {
    -20301: "La fecha de checkout debe ser estrictamente posterior a la fecha de checkin.",
    -20302: "Rango de fechas no valido o inconsistente.",
    -20303: "La habitacion no existe, pertenece a otro alojamiento o esta fuera de servicio.",
    -20304: "La habitacion seleccionada ya cuenta con una reserva confirmada/activa en ese periodo (Solapamiento detectado).",
    -20305: "El numero de personas solicitadas excede la capacidad maxima autorizada para la habitacion.",
    -20306: "Referencia de integridad no encontrada en clientes o alojamientos.",
    -20307: "Solicitud vacia o invalida de habitaciones.",
    -20308: "Cobertura incompleta de temporadas: existen noches dentro del rango sin temporada definida.",
    -20309: "Ambiguedad o superposicion detectada en el catalogo de temporadas.",
    -20310: "No existe tarifa vigente configurada para una o mas noches de la estadia.",
    -20311: "Error en el calculo monetario o importe invalido.",
    -20312: "Conflicto de concurrencia: recurso bloqueado por otra transaccion activa.",
    -20313: "Servicio no perteneciente al alojamiento o cantidad invalida.",
    -20314: "Fallo de integridad en el modelo de datos.",
    -20320: "Periodo de liquidacion invalido (anio o mes fuera de rango).",
    -20321: "Ya existe un corte mensual calculado para este alojamiento/mes con valores diferentes.",
    -20322: "El corte mensual ya se encuentra en estado cerrado o pagado.",
}

def parse_date(date_val: Any) -> dt.datetime:
    """Convierte strings, dates o datetimes a dt.datetime sin componente de hora."""
    if isinstance(date_val, dt.datetime):
        return date_val.replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(date_val, dt.date):
        return dt.datetime(date_val.year, date_val.month, date_val.day)
    if isinstance(date_val, str):
        # Admite YYYY-MM-DD
        d = dt.date.fromisoformat(date_val)
        return dt.datetime(d.year, d.month, d.day)
    raise ValueError(f"Tipo de fecha no compatible: {type(date_val)}")

class PLSQLService:
    """Servicio para invocar funciones, procedimientos y triggers de Entrega 2."""

    package_name = "pkg_turismouq"

    @staticmethod
    def cotizar_estadia(
        id_habitacion: int,
        fecha_in: Any,
        fecha_out: Any
    ) -> Tuple[bool, float, str]:
        """Invoca pkg_turismouq.fn_valor_estadia para calcular el precio acumulado noche a noche."""
        d_in = parse_date(fecha_in)
        d_out = parse_date(fecha_out)

        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    out_valor = cur.var(float)
                    plsql = f"""
                    BEGIN
                        :val := {PLSQLService.package_name}.fn_valor_estadia(:room_id, :d_in, :d_out);
                    END;
                    """
                    cur.execute(plsql, val=out_valor, room_id=id_habitacion, d_in=d_in, d_out=d_out)
                    valor = float(out_valor.getvalue())
                    return True, valor, "Cotizacion calculada satisfactoriamente."
        except oracledb.DatabaseError as exc:
            err = exc.args[0]
            code = getattr(err, "code", 0)
            msg = ERROR_MESSAGES.get(code, getattr(err, "message", str(exc)))
            return False, 0.0, f"ORA-{abs(code):05d}: {msg}"
        except Exception as exc:
            return False, 0.0, f"Error general: {str(exc)}"

    @staticmethod
    def crear_reserva(
        id_cliente: int,
        id_alojamiento: int,
        fecha_in: Any,
        fecha_out: Any,
        habitaciones: List[Tuple[int, int]],  # [(id_habitacion, personas), ...]
        servicios: Optional[List[Tuple[int, int]]] = None,  # [(id_servicio, cantidad), ...]
        confirmar: bool = True
    ) -> Tuple[bool, Optional[int], float, str]:
        """Invoca pkg_turismouq.sp_crear_reserva manejando colecciones y excepciones."""
        d_in = parse_date(fecha_in)
        d_out = parse_date(fecha_out)
        servicios = servicios or []

        assignments = []
        binds: Dict[str, Any] = {
            "customer": id_cliente,
            "lodging": id_alojamiento,
            "date_in": d_in,
            "date_out": d_out
        }

        for idx, (room_id, people) in enumerate(habitaciones, 1):
            assignments.append(f"v_rooms({idx}).id_habitacion := :room_{idx};")
            assignments.append(f"v_rooms({idx}).personas_hospedadas := :people_{idx};")
            binds[f"room_{idx}"] = room_id
            binds[f"people_{idx}"] = people

        for idx, (service_id, qty) in enumerate(servicios, 1):
            assignments.append(f"v_services({idx}).id_servicio := :service_{idx};")
            assignments.append(f"v_services({idx}).cantidad := :qty_{idx};")
            binds[f"service_{idx}"] = service_id
            binds[f"qty_{idx}"] = qty

        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    res_id_var = cur.var(int)
                    total_amount_var = cur.var(float)
                    binds["res_id"] = res_id_var
                    binds["total_amount"] = total_amount_var

                    plsql = f"""
                    DECLARE
                        v_rooms {PLSQLService.package_name}.lista_solicitudes_habitacion :=
                            {PLSQLService.package_name}.lista_solicitudes_habitacion();
                        v_services {PLSQLService.package_name}.lista_solicitudes_servicio :=
                            {PLSQLService.package_name}.lista_solicitudes_servicio();
                    BEGIN
                        v_rooms.EXTEND({len(habitaciones)});
                        v_services.EXTEND({len(servicios)});
                        {' '.join(assignments)}
                        {PLSQLService.package_name}.sp_crear_reserva(
                            :customer, :lodging, :date_in, :date_out,
                            v_rooms, v_services, :res_id, :total_amount
                        );
                    END;
                    """
                    cur.execute(plsql, binds)
                    new_id = int(res_id_var.getvalue())
                    total = float(total_amount_var.getvalue())
                    if confirmar:
                        conn.commit()
                    else:
                        conn.rollback()
                    return True, new_id, total, f"Reserva #{new_id} registrada con exito por un total de ${total:,.2f}"
        except oracledb.DatabaseError as exc:
            err = exc.args[0]
            code = getattr(err, "code", 0)
            msg = ERROR_MESSAGES.get(code, getattr(err, "message", str(exc)))
            return False, None, 0.0, f"ORA-{abs(code):05d}: {msg}"
        except Exception as exc:
            return False, None, 0.0, f"Error general al crear la reserva: {str(exc)}"

    @staticmethod
    def liquidar_mes(
        anio: int,
        mes: int,
        porcentaje_comision: float,
        id_alojamiento: Optional[int] = None
    ) -> Tuple[bool, int, int, str]:
        """Ejecuta pkg_turismouq.sp_liquidar_mes con cursor explicito parametrizado."""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    out_creadas = cur.var(int)
                    out_conservadas = cur.var(int)
                    plsql = f"""
                    BEGIN
                        {PLSQLService.package_name}.sp_liquidar_mes(
                            :p_anio, :p_mes, :p_pct, :p_alojamiento,
                            :p_creadas, :p_conservadas
                        );
                    END;
                    """
                    cur.execute(
                        plsql,
                        p_anio=anio,
                        p_mes=mes,
                        p_pct=porcentaje_comision,
                        p_alojamiento=id_alojamiento,
                        p_creadas=out_creadas,
                        p_conservadas=out_conservadas
                    )
                    conn.commit()
                    creadas = int(out_creadas.getvalue())
                    conservadas = int(out_conservadas.getvalue())
                    msg = f"Liquidacion completada: {creadas} cortes nuevos creados, {conservadas} cortes conservados sin cambios."
                    return True, creadas, conservadas, msg
        except oracledb.DatabaseError as exc:
            err = exc.args[0]
            code = getattr(err, "code", 0)
            msg = ERROR_MESSAGES.get(code, getattr(err, "message", str(exc)))
            return False, 0, 0, f"ORA-{abs(code):05d}: {msg}"
        except Exception as exc:
            return False, 0, 0, f"Error al ejecutar liquidacion: {str(exc)}"

    @staticmethod
    def actualizar_tarifa(id_tarifa: int, nuevo_precio: float) -> Tuple[bool, str]:
        """Actualiza el precio de una tarifa para disparar trg_auditar_tarifa."""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE tarifa SET precio_noche = :precio WHERE id_tarifa = :id_tarifa",
                        {"precio": nuevo_precio, "id_tarifa": id_tarifa}
                    )
                    conn.commit()
                    return True, f"Tarifa #{id_tarifa} actualizada exitosamente a ${nuevo_precio:,.2f}"
        except Exception as exc:
            return False, f"Error al actualizar tarifa: {str(exc)}"

    # Metodos auxiliares de catalogo para poblar selects en la UI
    @staticmethod
    def _fetch_df(sql: str, binds: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Ejecuta una consulta SQL nativa y devuelve un DataFrame de pandas sin advertencias de DBAPI2."""
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if binds:
                    cur.execute(sql, binds)
                else:
                    cur.execute(sql)
                if cur.description:
                    cols = [col[0].lower() for col in cur.description]
                    rows = cur.fetchall()
                    return pd.DataFrame(rows, columns=cols)
                return pd.DataFrame()

    @staticmethod
    def get_municipios() -> pd.DataFrame:
        sql = "SELECT id_municipio, nombre FROM municipio ORDER BY nombre"
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame([{"id_municipio": 1, "nombre": "Armenia"}, {"id_municipio": 2, "nombre": "Salento"}])

    @staticmethod
    def get_alojamientos(id_municipio: Optional[int] = None) -> pd.DataFrame:
        sql = "SELECT a.id_alojamiento, a.nombre, m.nombre AS municipio " \
              "FROM alojamiento a JOIN municipio m ON m.id_municipio = a.id_municipio"
        if id_municipio:
            sql += f" WHERE a.id_municipio = {id_municipio}"
        sql += " ORDER BY a.nombre"
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame([{"id_alojamiento": 1, "nombre": "Hotel Campestre Paraiso", "municipio": "Armenia"}])

    @staticmethod
    def get_habitaciones(id_alojamiento: Optional[int] = None) -> pd.DataFrame:
        sql = """
        SELECT h.id_habitacion, h.numero_habitacion, h.id_alojamiento, a.nombre AS alojamiento,
               th.nombre AS tipo_habitacion, th.capacidad_estandar AS capacidad,
               h.estado AS estado_habitacion
        FROM habitacion h
        JOIN alojamiento a ON a.id_alojamiento = h.id_alojamiento
        JOIN tipo_habitacion th ON th.id_tipo_habitacion = h.id_tipo_habitacion
        """
        if id_alojamiento:
            sql += f" WHERE h.id_alojamiento = {id_alojamiento}"
        sql += " ORDER BY a.nombre, h.numero_habitacion"
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame([{
                "id_habitacion": 1, "numero_habitacion": "101", "id_alojamiento": 1,
                "alojamiento": "Hotel Campestre Paraiso", "tipo_habitacion": "SUITE",
                "capacidad": 2, "estado_habitacion": "DISPONIBLE"
            }])

    @staticmethod
    def get_clientes(limit: int = 50) -> pd.DataFrame:
        sql = f"""
        SELECT c.id_cliente, u.nombre_completo, u.email, c.tipo_documento, c.numero_documento
        FROM cliente c
        JOIN usuario_sistema u ON u.id_usuario = c.id_usuario
        FETCH FIRST {limit} ROWS ONLY
        """
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame([{
                "id_cliente": 1, "nombre_completo": "Juan Perez",
                "email": "juan@turismouq.com", "tipo_documento": "CC", "numero_documento": "1094888001"
            }])

    @staticmethod
    def get_servicios(id_alojamiento: Optional[int] = None) -> pd.DataFrame:
        sql = "SELECT id_servicio, id_alojamiento, nombre, precio, tipo_cobro FROM servicio"
        if id_alojamiento:
            sql += f" WHERE id_alojamiento = {id_alojamiento}"
        sql += " ORDER BY nombre"
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame([{
                "id_servicio": 1, "id_alojamiento": 1, "nombre": "Tour Cafetero",
                "precio": 50000.0, "tipo_cobro": "POR_PERSONA"
            }])

    @staticmethod
    def get_auditorias(limit: int = 50) -> pd.DataFrame:
        sql = f"""
        SELECT id_auditoria, id_tarifa, usuario,
               TO_CHAR(fecha_modificacion, 'YYYY-MM-DD HH24:MI:SS') AS fecha_utc,
               precio_anterior, precio_nuevo,
               (precio_nuevo - precio_anterior) AS variacion,
               operacion, identificador_sentencia
        FROM auditoria_tarifa
        ORDER BY fecha_modificacion DESC, id_auditoria DESC
        FETCH FIRST {limit} ROWS ONLY
        """
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def get_liquidaciones(limit: int = 50) -> pd.DataFrame:
        sql = f"""
        SELECT l.id_liquidacion, a.nombre AS alojamiento, l.anio, l.mes,
               l.total_hospedaje, l.total_servicios,
               (l.total_hospedaje + l.total_servicios) AS base_total,
               l.porcentaje_comision, l.valor_comision, l.valor_neto_propietario,
               l.estado, TO_CHAR(l.fecha_calculo, 'YYYY-MM-DD HH24:MI') AS fecha_calculo
        FROM liquidacion_mensual l
        JOIN alojamiento a ON a.id_alojamiento = l.id_alojamiento
        ORDER BY l.anio DESC, l.mes DESC, a.nombre
        FETCH FIRST {limit} ROWS ONLY
        """
        try:
            return PLSQLService._fetch_df(sql)
        except Exception:
            return pd.DataFrame()

plsql_service = PLSQLService()
