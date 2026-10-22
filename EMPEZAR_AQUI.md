# Empezar aquí — TurismoUQ corregido

El esquema para usar la entrega es **`TURISMOUQ_E1`**. Ya contiene el modelo y la carga corregidos. El esquema original **`TURISMOUQ`** se conserva para comparación.

**No repitas el DDL ni `02_carga.sql` sobre `TURISMOUQ_E1`.** Para ver los informes solo necesitas conectar, verificar, refrescar la materializada y ejecutar las ocho consultas.

## 1. Abrir CMD y SQL*Plus

En CMD, ejecutar estas líneas. El `cd /d` debe realizarse antes de abrir SQL*Plus para resolver las rutas de los scripts:

```bat
cd /d "C:\Users\ASUS\Desktop\U_SEM7-8\BD_2\tourism\turismoUq"
chcp 65001
set "NLS_LANG=AMERICAN_AMERICA.AL32UTF8"
"C:\app\ASUS\product\21c\dbhomeXE\bin\sqlplus.exe" /nolog
```

Cuando aparezca `SQL>`, ya estás dentro de SQL*Plus.

## 2. Elegir tu contraseña del esquema corregido

Para la primera conexión después de la validación, elige una contraseña local desde el administrador. No se entrega ninguna contraseña temporal en archivos.

```sql
CONNECT / AS SYSDBA
ALTER SESSION SET CONTAINER = XEPDB1;
SHOW USER
SHOW CON_NAME
SPOOL OFF
SET ECHO OFF
SET VERIFY OFF
```

Debes ver `SYS` y `XEPDB1`. Escribe ahora únicamente:

```sql
PASSWORD TURISMOUQ_E1
```

Espera los mensajes de nueva contraseña y confirmación, e introdúcela en esos momentos. No pegues el siguiente bloque mientras SQL*Plus esté esperando tu respuesta. Se modifica la contraseña de `TURISMOUQ_E1`; el usuario original `TURISMOUQ` no se toca.

Este paso no hace falta en sesiones posteriores si ya conoces tu contraseña.

## 3. Conectar como usuario del proyecto

Escribe solamente esta línea y espera:

```sql
CONNECT TURISMOUQ_E1@localhost:1521/xepdb1
```

Cuando aparezca `Enter password:`, introduce la contraseña elegida. No la añadas al comando. Una vez vuelva `SQL>`, comprueba y configura la sesión:

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

Debes ver usuario `TURISMOUQ_E1` y contenedor `XEPDB1`.

## 4. Verificar y ejecutar los informes

Ejecuta uno por uno, esperando que termine cada archivo:

```sql
@scripts/verificar_entrega1.sql
```

```sql
@scripts/refrescar_ocupacion.sql
```

```sql
@03_consultas_analisis.sql
```

El segundo comando actualiza la instantánea de ocupación. El tercero ejecuta las ocho lecturas e inicializa los parámetros de consulta 5 con `2025-06-01` y `2025-07-31`, ambos incluidos. Para otro rango consulta [el README](README.md#consultas-y-reportes-posteriores).

Si un paso falla, conserva el mensaje completo. No repitas instalación ni carga para intentar corregirlo. Si estás en otro directorio, cierra SQL*Plus y vuelve a abrirlo después del `cd /d` del paso 1.

Para salir:

```sql
EXIT
```

## Qué está disponible

- [Resultado de validación](docs/entrega1/resultado_validacion.md): pruebas realizadas, datos y límites.
- [Contrato analítico](docs/entrega1/contrato_analitico.md): significado de los informes.
- [README](README.md): instalación nueva, migración y reproducción de pruebas.

La **Entrega 2 de PL/SQL sigue pendiente**. Esta corrección de Entrega 1 no implementa la función de estadía, el procedimiento de reserva, el cursor de liquidación, el paquete ni los disparadores.
