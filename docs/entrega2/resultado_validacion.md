# Validación de Entrega 2 — capa PL/SQL

Fecha: 22 de octubre de 2026, zona America/Bogota. **Resultado final: PASS.**

La [corrida final 2026-10-22_124147](../../evidencias/entrega2/2026-10-22_124147/resultado.json) aprobó **40 de 40 casos E2**, **23 de 23 regresiones E1**, las ocho consultas y la demostración de sustentación. Una [prueba adicional de migración](../../evidencias/entrega2/migracion-legado/resultado.json) aprobó cuatro controles sobre legado no vacío y contrato incompatible.

No son resultados estimados ni capturas construidas desde INSERT: los scripts se ejecutaron contra Oracle local. La [guía de sustentación](guia_sustentacion.md) permite repetir la demostración sin conservar sus cambios.

## Código y entorno

| Elemento | Valor |
|---|---|
| Base de los cambios | `a33fbccb3a7cb50930aa24dcdeb914a296eee0e4` |
| Identificación del código probado | SHA-256 de 32 archivos ejecutables en `resultado.json`; la base Git no se presenta como el commit que ya contenía la implementación. |
| Motor | Oracle Database XE 21c, versión 21.3.0.0.0 |
| Sistema | Windows 11, compilación 26200 |
| Clientes | SQL*Plus 21.3 y Python 3.14.5 con `python-oracledb` 26.0.1, cliente Oracle 21.3 |
| Servicio y PDB | `localhost:1521/xepdb1`, `XEPDB1` |
| Perfil de sesión | `READ COMMITTED`, calendario `GREGORIAN` |
| Esquema disponible para sustentar | `TURISMOUQ_E2` |

Se conservaron las cuentas `TURISMOUQ` y `TURISMOUQ_E1`. Las cuatro cuentas de la corrida E2 fueron creadas por el ejecutor; sus contraseñas aleatorias solo existieron en memoria. El usuario puede elegir después la contraseña de E2 desde SQL*Plus. No se restablecieron las contraseñas de los esquemas preservados.

La corrida final reutilizó el bootstrap propio acreditado por sus fechas de creación y volvió a instalar los objetos y ejecutar las pruebas. El manifiesto conserva esa procedencia en `resumed_from`. La prueba de migración adicional partió del DDL E1 del commit `06f5bd4`, con registros legados reales de fixture.

## Implementación comprobada

| Componente | Resultado observado |
|---|---|
| [Especificación](../../plsql/01_pkg_turismouq.pks) y [cuerpo](../../plsql/02_pkg_turismouq.pkb) | `PKG_TURISMOUQ` y `PACKAGE BODY` válidos. API, tipos, errores, valor de estadía, reserva, cursor mensual y validadores compartidos. |
| Función de estadía | Cotizaciones por tramos correctas; huecos, superposiciones, tarifa ausente, horas e importes excesivos rechazados. |
| Creación de reservas | Varias habitaciones y servicios del mismo alojamiento, precios capturados y total conciliado; errores propios y rollback parcial sin COMMIT oculto. |
| [Auditoría](../../plsql/03_trg_auditar_tarifa.sql) | UPDATE de precio con actor conectado, timestamp UTC e identificador común de sentencia; rollback revierte precios y eventos. |
| [Detalle](../../plsql/04_trg_reserva_habitacion.sql) y [cabecera](../../plsql/05_trg_reserva.sql) | Solapes rechazados, contigüidad aceptada, cancelación libera, reactivación conflictiva rechazada y ausencia de tabla mutante en los casos probados. |
| Liquidación | Solo FINALIZADA por mes del checkout, comisión obligatoria sobre hospedaje más servicios, sin multiplicar detalles y servicios. Repetición idéntica conserva el corte; diferencias se rechazan. |
| [Instalador](../../04_instalar_capa_plsql.sql) | Dos ejecuciones compatibles tanto en el esquema de entrega como en el de fixtures. Cinco objetos válidos y tres triggers compuestos habilitados. |

La compilación no dejó errores de `USER_ERRORS` con atributo ERROR. Oracle emitió tres advertencias: dos recomendaciones de rendimiento `PLW-07203` sobre parámetros OUT privados que podrían usar NOCOPY y una `PLW-06010` por el nombre de columna `VALUE` del catálogo NLS. Se mantuvo la copia convencional; las salidas públicas solo se consideran válidas al regresar sin excepción. El verificador distingue esas advertencias de un objeto inválido.

## Casos funcionales y concurrentes

Los [40 resultados detallados](../../evidencias/entrega2/2026-10-22_124147/pruebas_entrega2.json) contienen expectativa, observación, errores y limpieza por caso:

| Grupo | Casos | Comprobaciones principales |
|---|---:|---|
| F01–F08 | 8 | Una temporada, cruce, checkout excluido, 367 noches, datos inválidos, cobertura, historial estable y límite monetario. |
| R01–R05 | 5 | Varias habitaciones/servicios, capacidad, referencias, fallos posteriores a inserciones y rollback del llamador. |
| C01–C06 | 6 | Dos sesiones con commit/rollback, timeout, habitaciones independientes, orden inverso, precio concurrente y detalle contra cambio de cabecera. |
| T01–T04 | 4 | Formas de cruce, DML masivo, reactivación/cambio de fechas y reutilización de noches canceladas. |
| A01–A05 | 5 | Actor/UTC, 100 cambios en una sentencia, actualización sin cambio, rollback y fallo masivo. |
| L01–L08 | 8 | Mes del checkout, estados excluidos, sumas correctas, repetición, dos sesiones, atomicidad del lote, parámetros y legado sin metadatos. |
| I01–I04 | 4 | Compilación/reinstalación, EXECUTE sin DML, regresión E1 y preservación de originales. |

Resultados numéricos comprobados: 29/06–03/07 con noches a 100/150 produce **500**; después de cambiar junio a 120, una cotización nueva produce **540** y el contrato conserva **500**. La estadía larga de 367 noches a 10 produce **3.670**. La liquidación de prueba H=200, S=50 y porcentaje 12 conserva base **250**, comisión **30** y neto **220**. Dos habitaciones por 100+200 y servicios por 10+20 producen base **330**, no un producto cartesiano.

Los casos concurrentes usaron conexiones distintas y barreras explícitas. C05 empleó instrumentación temporal exclusiva de fixtures, con una señal autónoma para colocar el cambio de catálogo después de capturar precios. No hay transacciones autónomas en el paquete ni triggers productivos. La limpieza comprobó cero filas de fixtures, cero filas de MV y cero triggers temporales restantes.

## Regresión, migración y conservación

La [regresión E1](../../evidencias/entrega2/2026-10-22_124147/regresion_entrega1.json) conserva sus 23 IDs. Los casos del certificador se ejecutaron antes de instalar triggers E2; los 20 escenarios de consultas usaron un esquema dedicado sin esos triggers, porque prueban poblaciones analíticas y legadas. Las [ocho consultas](../../evidencias/entrega2/2026-10-22_124147/ocho_consultas_con_e2.log) y el contraste de binds se ejecutaron sobre el esquema con E2 instalado. No se deshabilitaron triggers productivos para aprobar los 40 casos E2.

Los hashes [antes](../../evidencias/entrega2/2026-10-22_124147/originales_antes.json) y [después](../../evidencias/entrega2/2026-10-22_124147/originales_despues.json) son idénticos en las 21 tablas de `TURISMOUQ` y las 22 de `TURISMOUQ_E1`. El esquema E2 mantiene 25.000 reservas, 42.735 líneas de servicios y 32.993 tramos de precio aplicado. Auditoría y liquidaciones quedan sin filas de demostración.

Los cuatro controles [MIG-L01–MIG-L04](../../evidencias/entrega2/migracion-legado/resultado.json) comprobaron conservación de las columnas originales en 22 tablas, timestamp e importes existentes, nuevos metadatos NULL sin inferencias, segunda ejecución sin cambios y rechazo de `ID_SENTENCIA RAW(8)` con ORA-20401 antes de alterar la estructura. La migración no asignó un porcentaje ficticio a la comisión histórica de prueba.

## Demostración ejecutada

La [salida real de la demostración](../../evidencias/entrega2/2026-10-22_124147/demostracion_sustentacion.log) registró:

- Habitación 1, dos noches del 14 al 16 de enero de 2027: cotización **758.000**.
- Rechazos esperados `-20301` por checkout, `-20305` por capacidad y `-20304` por solape.
- Auditoría del cambio de tarifa **379.000 → 379.001**, con `TURISMOUQ_E2` como actor, UTC e ID de sentencia; rollback restaura tarifa y auditoría.
- Alojamiento 1, enero de 2025: hospedaje **29.469.000**, servicios **5.638.000**, base **35.107.000**, comisión de prueba 12 % = **4.212.840**, neto **30.894.160**.
- Segunda liquidación: crea cero y conserva un corte con el mismo ID.

El rollback final restauró las filas de las 22 tablas, comprobadas mediante fingerprint independiente del script. Las identidades pueden consumir números pese al rollback; un hueco de ID no demuestra que haya quedado una reserva guardada.

## Límites declarados

La GUI no forma parte de este incremento. No se implementaron pagos, dispersión, jobs, recálculo contable ni API de edición de reservas. La igualdad de un corte se comprueba por importes y política almacenados, sin garantizar identidad inmutable de sus reservas fuente.

Los triggers combinan fases por fila y sentencia. Su funcionamiento técnico está probado; no se obtuvo una aceptación expresa de la profesora sobre la clasificación literal de la rúbrica. El usuario autorizó adoptar esta solución sin esperar esa respuesta.

El perfil probado es Windows/SQL*Plus/python-oracledb y READ COMMITTED. No se acredita ejecución con SQLcl, Debian o aislamiento SERIALIZABLE. Las pruebas respaldan los casos descritos, sin prometer latencias o rendimiento no medidos.
