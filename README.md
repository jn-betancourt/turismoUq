# TurismoUQ — Entrega 1

Modelo de reservas turísticas para Oracle Database XE 21c, con 22 tablas, carga sintética reproducible y ocho consultas de análisis. Las definiciones de métricas, procedencia de precios y límites están en [el contrato analítico](docs/entrega1/contrato_analitico.md).

Para usar el esquema local ya preparado, seguir [EMPEZAR_AQUI.md](EMPEZAR_AQUI.md). La [validación final](docs/entrega1/resultado_validacion.md) aprobó 23 casos y las ocho consultas; [su evidencia](evidencias/entrega1/2026-10-22_114219/resultado.json) registra el entorno y los hashes del código ejecutado.

Esta corrección conserva las reservas y los importes contratados. La capa PL/SQL de Entrega 2 —función de estadía, procedimiento de reserva, cursor de liquidación, paquete y disparadores— sigue pendiente.

## Archivos y responsabilidades

| Archivo | Finalidad |
|---|---|
| [scripts/crear_tablespace.sql](scripts/crear_tablespace.sql) | Infraestructura administrativa, separada del modelo. |
| [01_DDL_TURISMOUQ_ORACLE21C.sql](01_DDL_TURISMOUQ_ORACLE21C.sql) | Instalación nueva de las 22 tablas y sus índices; requiere esquema vacío. |
| [02_carga.sql](02_carga.sql) | Carga inicial; rechaza tablas con datos y captura los precios aplicados por tramo. |
| [scripts/verificar_entrega1.sql](scripts/verificar_entrega1.sql) | Aceptación de estructura, volúmenes e integridad; falla si falta evidencia histórica. |
| [scripts/preparar_analitica.sql](scripts/preparar_analitica.sql) | Preparación de cuatro vistas de apoyo y una vista materializada. |
| [scripts/refrescar_ocupacion.sql](scripts/refrescar_ocupacion.sql) | Refresco completo explícito de la materializada antes de cada reporte. |
| [03_consultas_analisis.sql](03_consultas_analisis.sql) | Lanzador de las ocho consultas; no crea objetos, carga datos ni refresca la MV. |
| [consultas/](consultas/) | Los ocho SELECT canónicos, incluido el SELECT parametrizado independiente. |
| [migraciones/001_tramos_tarifarios.sql](migraciones/001_tramos_tarifarios.sql) | Actualización estructural de una base previa; no reconstruye ni rellena precios. |
| [schema.dbml](schema.dbml), [schema.dbdiagram](schema.dbdiagram) y [definicion_entidades.md](definicion_entidades.md) | Representación y explicación del modelo. El DDL es el contrato ejecutable. |

## Entorno local y separación de esquemas

El esquema original `TURISMOUQ` se conserva. El esquema de la entrega corregida es `TURISMOUQ_E1`; las pruebas de reproducción usan esquemas aislados. No se restablece la contraseña ni se vuelve a cargar el esquema original para aplicar esta corrección.

En el equipo Windows observado se utiliza SQL*Plus 21.3, servicio `localhost:1521/xepdb1` y PDB `XEPDB1`. Para la entrada interactiva de contraseña se prefiere **CMD**, donde el usuario comprobó que aparece el prompt. No se incluye ninguna contraseña en argumentos, scripts o registros.

La corrida final contrastó SQL*Plus y Python con `python-oracledb` 26.0.1. El SQLcl 21.2 local presentó un fallo de carga de su clase principal; no se acredita una ejecución con SQLcl ni con Debian. El [informe de validación](docs/entrega1/resultado_validacion.md) identifica las versiones y los resultados obtenidos.

## Abrir una sesión en Windows

Desde CMD, situarse en la raíz de este repositorio **antes de abrir SQL*Plus**. Este directorio de trabajo es un requisito de los lanzadores y sus rutas `@`; mantenerlo durante toda la ejecución:

```bat
cd /d "C:\Users\ASUS\Desktop\U_SEM7-8\BD_2\tourism\turismoUq"
chcp 65001
set "NLS_LANG=AMERICAN_AMERICA.AL32UTF8"
"C:\app\ASUS\product\21c\dbhomeXE\bin\sqlplus.exe" /nolog
```

Los archivos están en UTF-8. Los siguientes bloques SQL se ejecutan en SQL*Plus, cuando aparece `SQL>`.

## Infraestructura y usuario de una instalación nueva

Esta sección se usa únicamente si todavía no existe el esquema de destino. Si `TURISMOUQ_E1` ya fue preparado durante la validación, pasar a la sección siguiente para elegir su contraseña local; no repetir DDL ni carga.

Como administrador local, conectar y comprobar el contenedor:

```sql
CONNECT / AS SYSDBA
ALTER SESSION SET CONTAINER = XEPDB1;
SHOW USER
SHOW CON_NAME

SELECT username FROM dba_users WHERE username = 'TURISMOUQ_E1';
SELECT tablespace_name FROM dba_tablespaces
WHERE tablespace_name = 'TS_HISTORICO_RESERVAS';
```

`SHOW CON_NAME` debe indicar `XEPDB1`. Si el usuario ya existe, revisar su estado y no recrearlo. El script de infraestructura conserva un tablespace existente sin modificarlo.

El script recibe **dos argumentos obligatorios**: perfil y ruta. Elegir una sola alternativa:

```sql
-- OMF: solo si DB_CREATE_FILE_DEST ya esta configurado; no lo cambia.
@scripts/crear_tablespace.sql OMF SIN_RUTA
```

```sql
-- RUTA: nombre absoluto de un archivo del servidor Oracle.
@scripts/crear_tablespace.sql RUTA "C:\APP\ASUS\PRODUCT\21C\ORADATA\XE\XEPDB1\TS_HISTORICO_RESERVAS01.DBF"
```

La segunda alternativa corresponde al directorio observado en este servidor Windows, donde `DB_CREATE_FILE_DEST` estaba vacío. En un servidor Linux se proporciona su propia ruta absoluta. Los parámetros no admiten comillas simples ni el carácter `~`. El script no borra ni reutiliza archivos existentes ni modifica la configuración OMF de la instancia.

Solo cuando se haya confirmado que `TURISMOUQ_E1` no existe:

```sql
CREATE USER turismouq_e1 NO AUTHENTICATION
    DEFAULT TABLESPACE users
    TEMPORARY TABLESPACE temp
    QUOTA UNLIMITED ON users;

GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW,
      CREATE MATERIALIZED VIEW, CREATE SEQUENCE
TO turismouq_e1;

ALTER USER turismouq_e1 QUOTA UNLIMITED ON ts_historico_reservas;
```

El usuario creado con `NO AUTHENTICATION` necesita una contraseña antes de conectarse. El paso siguiente la establece desde el prompt de SQL*Plus.

## Elegir la contraseña local y conectar al esquema corregido

Después de la validación, el usuario puede elegir una contraseña para `TURISMOUQ_E1` desde una sesión `SYS` en `XEPDB1`. Las credenciales temporales de las pruebas no forman parte del repositorio. Abrir SQL*Plus desde la raíz del repositorio como se indicó arriba y ejecutar:

```sql
CONNECT / AS SYSDBA
ALTER SESSION SET CONTAINER = XEPDB1;
SHOW USER
SHOW CON_NAME
SPOOL OFF
SET ECHO OFF
SET VERIFY OFF
```

Confirmar usuario `SYS` y contenedor `XEPDB1`. Después, ejecutar **solo** este comando:

```sql
PASSWORD TURISMOUQ_E1
```

Esperar los mensajes e introducir y confirmar la contraseña local. No pegar otro bloque mientras SQL*Plus espera una respuesta. Este comando se refiere al esquema corregido; no utilizarlo sobre `TURISMOUQ`.

Después, escribir únicamente:

```sql
CONNECT TURISMOUQ_E1@localhost:1521/xepdb1
```

Esperar `Enter password:` e introducir la contraseña. Una vez vuelva `SQL>`, comprobar:

```sql
SHOW USER
SHOW CON_NAME
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
SET SQLBLANKLINES ON
SET DEFINE OFF
SET SERVEROUTPUT ON
SET PAGESIZE 200
SET LINESIZE 240
SET TRIMSPOOL ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
WHENEVER OSERROR EXIT FAILURE
```

Si no aparece el prompt o la conexión falla, conservar el error y revisar la sesión; no asumir que es necesario restablecer contraseñas. También puede iniciarse SQL*Plus desde una nueva ventana CMD con `-L TURISMOUQ_E1@localhost:1521/xepdb1`, sin incluir la contraseña. En esa ventana nueva, ejecutar primero el mismo `cd /d` a la raíz del repositorio.

## Instalar, cargar y verificar una vez

Ejecutar conectado al propietario de un esquema nuevo. El modelo rechaza `SYS`, `SYSTEM` y esquemas que ya tienen tablas.

1. Ejecutar `@01_DDL_TURISMOUQ_ORACLE21C.sql`.
2. Antes de la carga, fijar los **dos `DEFINE` de configuración** que aparecen al inicio de `02_carga.sql`: `carga_semilla` y `carga_referencia`. Esta última incluye fecha, hora y región. No confundirlos con los binds de la consulta 5.
3. Ejecutar `@02_carga.sql` una sola vez, con las 22 tablas todavía vacías.
4. Ejecutar `@scripts/verificar_entrega1.sql` y revisar su finalización.
5. Ejecutar `@scripts/preparar_analitica.sql` una vez. Si la MV ya existe, revisar su definición; este script no la elimina automáticamente.
6. Ejecutar `@scripts/refrescar_ocupacion.sql` antes de producir el reporte.
7. Ejecutar `@03_consultas_analisis.sql`.

La carga conserva los precios y tipos de temporada aplicados por intervalos `[inicio, fin)`. La semilla y la referencia temporal explícita permiten comparar instalaciones nuevas con la misma versión de Oracle y del código. Los volúmenes mínimos requeridos son 12 municipios, 60 alojamientos, 400 habitaciones, 3.000 clientes, 25.000 reservas y 40.000 líneas de servicios; son criterios de aceptación, no resultados certificados por este README.

Los scripts contienen DDL y la carga realiza confirmaciones. Si una fase falla, conservar la salida y diagnosticar su estado; un `ROLLBACK` final no deshace toda la instalación. No solucionar una carga parcial ejecutándola de nuevo ni borrando datos automáticamente.

## Consultas y reportes posteriores

Abrir SQL*Plus con la raíz del repositorio como directorio de trabajo, conectar al esquema corregido, ejecutar el verificador, refrescar explícitamente la materializada y ejecutar el lanzador de consultas. No repetir instalación, carga ni creación de la MV. La ejecución desde otro directorio no está admitida por este recorrido: se observó un fallo de resolución de rutas anidadas en SQL*Plus 21.3.

`03_consultas_analisis.sql` contiene únicamente la orquestación de las ocho lecturas. La consulta 5 usa [un lanzador SQL*Plus](scripts/ejecutar_consulta_parametrizada_sqlplus.sql) que declara, inicializa y valida sus binds en la misma conexión; sus valores iniciales son `2025-06-01` y `2025-07-31`, incluidos ambos días.

Para otro rango, cambiar esos dos valores en el lanzador, o declarar/asignar los binds en una sesión y ejecutar primero [su validación](scripts/validar_parametros_consulta.sql) y después [el SELECT canónico](consultas/05_consulta_parametrizada.sql). El formato es estrictamente `YYYY-MM-DD`, las fechas deben existir y el inicio no puede superar al final. `9999-12-31` no se admite como final porque el filtro necesita calcular el día siguiente. Un cliente distinto suministra ambos binds como texto; no debe enviar comandos `VARIABLE` o `EXEC` al motor SQL.

La MV utiliza `REFRESH COMPLETE ON DEMAND`: admite desfase hasta el siguiente refresco explícito. El refresco escribe datos materializados y se realiza sin trabajo transaccional pendiente. No se instala un job diario ni se presenta la MV como control de disponibilidad operativa.

## Una base ya cargada con el modelo anterior

Con respaldo y conectado a su propietario, [la migración](migraciones/001_tramos_tarifarios.sql) crea solamente la tabla de tramos y el índice que falten. Verifica el contrato de objetos ya existentes y falla si es incompatible. No cambia importes previos, no recarga reservas ni calcula un supuesto precio histórico a partir de `TARIFA` actual.

Si un detalle de habitación carece de tramos, el informe de temporada conserva su importe como **`SIN DESGLOSE HISTORICO`**. Ese análisis es parcial. Si los tramos solo cubren parte de la estadía, tampoco se certifica el informe. El verificador falla hasta que exista evidencia suficiente y se concilien cobertura, no solapamiento e importe. Hacer coincidir la suma de tarifas actuales con un total antiguo no acredita esa evidencia.

El esquema original local se mantiene para comparación. La entrega corregida y las pruebas aisladas no requieren alterar sus datos ni su contraseña.

## Validación y evidencia

La ayuda del [ejecutor de pruebas](tests/validar_local.py) describe su interfaz:

```bat
python tests/validar_local.py --help
```

La ejecución necesita Python y `oracledb==26.0.1`, declarado en [tests/requirements.txt](tests/requirements.txt). Puede instalarse con `python -m pip install -r tests/requirements.txt`; el ejecutor también reconoce dependencias locales en `.validation-deps`. El modo utilizado requiere las bibliotecas del cliente Oracle. El ejecutor fija el directorio de trabajo de sus procesos SQL*Plus a la raíz del repositorio.

| Opción | Valor predeterminado o finalidad |
|---|---|
| `--schema-prefix` | `TURISMOUQ_E1`; crea tres esquemas nuevos: el prefijo, `_REPRO` y `_TEST`. Rechaza cuentas existentes. |
| `--service` | `localhost:1521/xepdb1`. |
| `--pdb` | `XEPDB1`. |
| `--sqlplus` | Ejecutable SQL*Plus detectado en `PATH`, o `sqlplus`. |
| `--oracle-client-lib` | Directorio de bibliotecas: `ORACLE_HOME/bin` si está definido; en caso contrario, directorio del SQL*Plus detectado. Puede fijarse explícitamente para el cliente instalado. |
| `--preserve-schema` | `TURISMOUQ`; debe ser distinto de los tres esquemas de pruebas. |

La [corrida final](evidencias/entrega1/2026-10-22_114219/resultado.json) registra entorno, código, 23 casos aprobados y ocho consultas ejecutadas. La [equivalencia del esquema de entrega](evidencias/entrega1/2026-10-22_114219/equivalencia_esquema_entrega.json) acredita que `TURISMOUQ_E1` coincide con el esquema de la corrida final en las 22 tablas, cuatro vistas de apoyo y la definición y 2.220 filas de la MV. El [informe](docs/entrega1/resultado_validacion.md) explica su alcance; mostrar la ayuda del ejecutor por sí solo no constituye una validación.
