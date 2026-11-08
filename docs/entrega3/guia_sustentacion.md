# TurismoUQ · Entrega 3

La entrega se ejecuta en **Oracle XE 21c / XEPDB1**. Este equipo ya tiene `TURISMOUQ_E3` con la carga sintética, los objetos de las tres entregas, los índices, los roles y las cuentas de demostración. Los esquemas anteriores conservan sus datos y claves.

## Usar la GUI en Windows

En SQL*Plus, en una sesión administrativa local, elige una clave para la cuenta que vas a usar. Escribe cada orden `PASSWORD` por separado y espera los dos prompts; las contraseñas se ingresan de forma interactiva.

```sql
CONNECT / AS SYSDBA
ALTER SESSION SET CONTAINER = XEPDB1;
PASSWORD TURISMOUQ_E3_USR_RECEP
```

Abre [run_app.cmd](../../run_app.cmd). Elige **Otro**, escribe `TURISMOUQ_E3_USR_RECEP` como usuario y `TURISMOUQ_E3` como esquema propietario. Usa `localhost:1521/xepdb1` y pulsa **Probar Conexión**. Para una prueba rápida con la carga inicial, busca la habitación de ID 1 (su alojamiento se puede consultar en `V_E3_HABITACIONES`) y usa del 9 al 10 de enero de 2027. El documento del cliente de prueba se obtiene de `V_E3_CLIENTES` para `ID_CLIENTE = 101`. **Simular operación** permite recorrer el flujo sin guardar cambios. El registro real pide el monto recibido y confirmación. La aplicación registra un pago recibido; no cobra tarjetas ni contacta pasarelas.

| Cuenta de ejemplo | Rol (prefijo `TURISMOUQ_E3_`) | Acceso |
| --- | --- | --- |
| `TURISMOUQ_E3_USR_RECEP` | `RECEPCION` | Consulta catálogo, identidad mínima y comprobantes propios; registra reserva y pago insertando en una vista. Sin tablas ni ejecución de paquetes. |
| `TURISMOUQ_E3_USR_ADMIN` | `ADMIN_ALOJAMIENTO` | Lee tarifas y modifica únicamente `PRECIO_NOCHE`; el trigger existente audita el cambio. Este rol tiene alcance sobre el catálogo de la plataforma. |
| `TURISMOUQ_E3_USR_GERENTE` | `GERENTE` | Lee agregados por alojamiento y mes de entrada, sin datos personales ni cambios. |
| `TURISMOUQ_E3_USR_AUDITOR` | `AUDITOR` | Lee eventos de cambios de tarifas. |
| `TURISMOUQ_E3` | Propietario | Administración del esquema, módulos E3 y módulos históricos. Usar para la sustentación técnica. |

El perfil limita a 3 sesiones simultáneas, 15 minutos de inactividad y 240 minutos de conexión. Después de 5 intentos fallidos, Oracle bloquea la cuenta durante una hora. Las cuentas de demostración se crean sin contraseña. Selecciona una clave solo para las que necesitas.

## Instalar en un esquema limpio

Ejecuta SQL*Plus desde la raíz del repo. Como SYS en `XEPDB1`, crea el tablespace y un propietario **nuevo** siguiendo [README](../../README.md): cuotas en `USERS` y `TS_HISTORICO_RESERVAS`; privilegios `CREATE SESSION`, `CREATE TABLE`, `CREATE VIEW`, `CREATE MATERIALIZED VIEW`, `CREATE SEQUENCE`, `CREATE PROCEDURE` y `CREATE TRIGGER`. Para los scripts de seguridad el propietario debe empezar por `TURISMOUQ_`. La evidencia se obtuvo con el nombre `TURISMOUQ_E3`. Configura su contraseña con `PASSWORD` antes de conectarte como propietario.

1. Como propietario, ejecuta `@01_DDL_TURISMOUQ_ORACLE21C.sql`, `@02_carga.sql` y `@scripts/verificar_entrega1.sql`. La medición reproducida usó la semilla y referencia incluidas en la carga.
2. Ejecuta `@scripts/preparar_analitica.sql` y `@04_instalar_capa_plsql.sql`.
3. Ejecuta `@06_instalar_entrega3.sql`. Se agrega una tabla para asociar el token de recepción a su pago y se instala el acceso por vistas.
4. Ejecuta `@07_crear_indices_entrega3.sql`. Si vas a medir el antes y después, **omite** este paso: el ejecutor de medición aplica este archivo entre las dos corridas.
5. Como SYS en XEPDB1, comprueba que `RESOURCE_LIMIT=TRUE`. Ejecuta `@08_configurar_seguridad_entrega3.sql TURISMOUQ_E3` y, para la GUI con cuentas de prueba, `@09_preparar_cuentas_entrega3.sql TURISMOUQ_E3`. Cambia el argumento si elegiste otro propietario. Ejecuta estos scripts una vez por esquema.

Para instalar sobre una copia ya cargada con Entrega 2, empieza en el paso 3. Los instaladores ejecutan DDL, así que inicia sin trabajo pendiente. El validador no modifica cuentas de Entregas 1 o 2.

## Sustentación y resultados

**Transacciones.** Como propietario ejecuta `@10_demostracion_entrega3.sql`. El primer intento genera una reserva confirmada y un pago aprobado. En el segundo intento se crea la reserva antes de comprobar el monto; el monto incorrecto dispara `ORA-20401` y `ROLLBACK TO SAVEPOINT` revierte solo ese intento. El primer trabajo sigue visible en la misma sesión. La demostración revierte también ese trabajo al terminar. El procedimiento no ejecuta `COMMIT`; el llamador decide. Desde la vista, la sentencia `INSERT` revierte completa si falla el trigger; Oracle no permite controles de transacción dentro de un trigger.

**Concurrencia.** [El ejecutor](../../tests/validar_entrega3.py) abre dos sesiones. El control reproduce el patrón leer disponibilidad e insertar en una tabla desechable sin el bloqueo ni los triggers: ambas sesiones leen 0 y confirman dos filas solapadas. Con la vista real, A registra sin confirmar y B queda en `enq: TX - row lock contention`, observado en `V$SESSION` con el SID de A como bloqueante. Al confirmar A, B vuelve a leer el estado y recibe `ORA-20304`; queda un pago y una reserva. Si A excede la espera de cinco segundos, la capa PL/SQL devuelve `ORA-20312`. El control no deshabilita ningún trigger de producción.

**Índices.** Se midieron 15 ejecuciones calientes por caso, más una de calentamiento, con los mismos parámetros y resultados. Los planes incluyen filas y buffers reales de `DBMS_XPLAN.DISPLAY_CURSOR`.

| Caso | Buffers por ejecución, antes → después | Mediana de cliente, ms | Plan después |
| --- | ---: | ---: | --- |
| Llegadas de un alojamiento en un día | 220,00 → 4,50 | 0,727 → 0,268 | Compuesto por alojamiento y fecha de entrada |
| Pagos de un día | 374,19 → 48,12 | 26,553 → 0,209 | Función `TRUNC(fecha_pago)` |
| Salidas finalizadas de un día | 219,50 → 15,50 | 0,943 → 0,184 | Compuesto por estado y fecha de salida |
| Pagos de todo el período (45.723 filas) | 373,12 → 373,12 | 28,249 → 29,043 | Escaneo completo antes y después |

En el último caso, casi toda la tabla califica y sumar `MONTO` exige leerla: recorrer el índice y luego visitar las filas por `ROWID` no compensa. No se forzó el índice. La mediana depende del entorno y de la caché; las lecturas lógicas permiten comparar el trabajo del motor. Los índices agregan espacio y mantenimiento de escritura.

**Seguridad.** Se probaron los cuatro roles con cuentas independientes, accesos permitidos y denegados, aislamiento del comprobante por usuario y rechazo de una cuarta sesión (`ORA-02391`). La GUI es una ayuda para operar el esquema; los controles se aplican en Oracle y también rigen fuera del navegador.

```bat
.venv\Scripts\python.exe tests\medir_indices_entrega3.py --schema TURISMOUQ_E3_OTRA --output evidencias\entrega3_repeticion
.venv\Scripts\python.exe tests\validar_entrega3.py --schema TURISMOUQ_E3 --output evidencias\entrega3_repeticion
```

Ambos ejecutores piden la clave del propietario y necesitan autenticación administrativa local, SQL*Plus y `oracledb`. Mide en un esquema sin los índices E3, con la misma carga; la prueba funcional requiere los roles y el perfil y está diseñada para una base de validación sin uso concurrente. La prueba funcional crea y borra sus propias cuentas temporales. Se revierten o eliminan las filas creadas durante la validación, pero las columnas de identidad pueden consumir números.

Evidencia: [mediciones](../../evidencias/entrega3/indices.json), [atomicidad, sesiones y permisos](../../evidencias/entrega3/validacion.json), [GUI](../../evidencias/entrega3/gui.json) y [planes antes/después](../../evidencias/entrega3).
