"""Gestor de conexion con Oracle Database XE 21c en Thin Mode."""
import time
from contextlib import contextmanager
from typing import Generator, Optional, Tuple, Dict, Any
import oracledb
from app.config import (
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_SERVICE,
    DEFAULT_DB_USER,
    DEFAULT_DB_PASSWORD
)

class DatabaseConnectionManager:
    """Administrador de conexiones Oracle en modo Thin."""

    def __init__(self):
        self.host = DEFAULT_DB_HOST
        self.port = DEFAULT_DB_PORT
        self.service_name = DEFAULT_DB_SERVICE
        self.user = DEFAULT_DB_USER
        self.password = DEFAULT_DB_PASSWORD

    def update_credentials(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        service_name: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        if host is not None:
            self.host = host.strip()
        if port is not None:
            self.port = int(port)
        if service_name is not None:
            self.service_name = service_name.strip()
        if user is not None:
            self.user = user.strip()
        if password is not None:
            self.password = password

    @property
    def dsn(self) -> str:
        return f"{self.host}:{self.port}/{self.service_name}"

    def connect(self) -> oracledb.Connection:
        """Crea una nueva conexion e inicializa las directivas de sesion."""
        conn = oracledb.connect(
            user=self.user,
            password=self.password,
            dsn=self.dsn
        )
        # Inicializar sesion segun contrato del proyecto
        with conn.cursor() as cursor:
            cursor.execute("ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN'")
            cursor.execute("ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED")
        return conn

    @contextmanager
    def get_connection(self) -> Generator[oracledb.Connection, None, None]:
        """Context manager seguro para obtener y cerrar conexiones."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def test_connection(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Verifica la conectividad y devuelve metadatos de la sesion."""
        t_start = time.perf_counter()
        try:
            with self.get_connection() as conn:
                latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT USER AS current_user, "
                        "SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name, "
                        "SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name, "
                        "VALUE AS calendar "
                        "FROM nls_session_parameters "
                        "WHERE parameter = 'NLS_CALENDAR'"
                    )
                    row = cur.fetchone()
                    meta = {
                        "user": row[0] if row else self.user,
                        "container": row[1] if row else "",
                        "database": row[2] if row else "",
                        "calendar": row[3] if row else "",
                        "version": conn.version,
                        "latency_ms": latency_ms,
                        "thin_mode": conn.thin
                    }
                    return True, "Conexion exitosa con Oracle XE 21c", meta
        except oracledb.DatabaseError as exc:
            err = exc.args[0]
            code = getattr(err, "code", 0)
            msg = getattr(err, "message", str(exc))
            return False, f"ORA-{code:05d}: {msg}", {"code": code, "error": msg}
        except Exception as exc:
            return False, f"Error de red o configuracion: {str(exc)}", {"error": str(exc)}

# Instancia singleton para compartir estado entre componentes
db_manager = DatabaseConnectionManager()
