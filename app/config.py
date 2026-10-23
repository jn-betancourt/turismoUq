"""Configuracion centralizada de la aplicacion TurismoUQ."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno si existe archivo .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = Path(__file__).resolve().parent
CONSULTAS_DIR = BASE_DIR / "consultas"
PLSQL_DIR = BASE_DIR / "plsql"
SCRIPTS_DIR = BASE_DIR / "scripts"

# Configuracion de conexion Oracle XE 21c (Thin Mode)
DEFAULT_DB_HOST = os.getenv("ORACLE_HOST", "localhost")
DEFAULT_DB_PORT = int(os.getenv("ORACLE_PORT", "1521"))
DEFAULT_DB_SERVICE = os.getenv("ORACLE_SERVICE", "xepdb1")
DEFAULT_DB_USER = os.getenv("ORACLE_USER", "TURISMOUQ_E2")
DEFAULT_DB_PASSWORD = os.getenv("ORACLE_PASSWORD", "")

# Informacion de consultas analiticas
CONSULTAS_INFO = {
    1: {
        "titulo": "1. Ocupacion por Municipio y Mes (PIVOT)",
        "archivo": "01_ocupacion_municipio_mes.sql",
        "descripcion": "Calcula el porcentaje de ocupacion bruta sobre el inventario actual de habitaciones por municipio mes a mes utilizando PIVOT.",
        "tecnica": "PIVOT / Calendario continuo"
    },
    2: {
        "titulo": "2. Ingresos por Municipio, Tipo y Temporada (ROLLUP)",
        "archivo": "02_ingresos_temporada.sql",
        "descripcion": "Total de hospedaje contratado desglosado por municipio, tipo de alojamiento y temporada aplicada con subtotales jerarquicos ROLLUP y GROUPING.",
        "tecnica": "ROLLUP / GROUPING / GROUPING_ID"
    },
    3: {
        "titulo": "3. Top 3 Alojamientos por Municipio (RANK)",
        "archivo": "03_top_alojamientos.sql",
        "descripcion": "Identifica los tres alojamientos con mayor facturacion (hospedaje + servicios) por cada municipio utilizando funciones de ventana RANK con PARTITION BY.",
        "tecnica": "RANK () OVER (PARTITION BY)"
    },
    4: {
        "titulo": "4. Variacion Mensual y Anual de Ingresos (LAG)",
        "archivo": "04_variacion_ingresos.sql",
        "descripcion": "Compara el ingreso mes a mes y contra el mismo mes del anio anterior usando LAG sobre el horizonte continuo de meses.",
        "tecnica": "LAG () OVER (ORDER BY mes)"
    },
    5: {
        "titulo": "5. Consulta Parametrizada por Rango de Fechas",
        "archivo": "05_consulta_parametrizada.sql",
        "descripcion": "Filtra reservas cuyo check-in se encuentre en un rango de fechas mediante variables de enlace (:fecha_ini, :fecha_fin), calculando ticket promedio y estancia media.",
        "tecnica": "Variables de enlace (Binds) / Agregacion"
    },
    6: {
        "titulo": "6. Ocupacion Critica sobre Vista Materializada (MV)",
        "archivo": "06_ocupacion_materializada.sql",
        "descripcion": "Consulta gerencial sobre MV_OCUPACION_MENSUAL (BUILD IMMEDIATE, REFRESH COMPLETE ON DEMAND) filtrando alojamientos con ocupacion menor al umbral critico (< 30%).",
        "tecnica": "Vista Materializada / Filtros gerenciales"
    },
    7: {
        "titulo": "7. Composicion de Ingresos Hospedaje vs Servicios (UNPIVOT)",
        "archivo": "07_composicion_ingresos.sql",
        "descripcion": "Descompone las fuentes de ingreso de cada municipio y anio mediante UNPIVOT y calcula la participacion porcentual de cada concepto.",
        "tecnica": "UNPIVOT / Funciones de ventana analiticas"
    },
    8: {
        "titulo": "8. Anticipacion, Duracion y Cancelaciones por Temporada",
        "archivo": "08_anticipacion_cancelaciones.sql",
        "descripcion": "Analiza el comportamiento de reserva segun temporada: antelacion promedio y mediana (percentiles), tasa de cancelacion y estancia promedio.",
        "tecnica": "PERCENTILE_CONT / Agregacion avanzada"
    }
}
