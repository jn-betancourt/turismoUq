# Validación de TurismoUQ — Entrega 1

Fecha: 22 de octubre de 2026. La **corrida final aprobó 23 de 23 casos**, ejecutó las ocho consultas y reprodujo los datos de las 22 tablas en dos esquemas nuevos iniciados con calendarios distintos. La comparación del esquema original de 21 tablas no detectó cambios en sus filas.

Este informe conserva el estado y la evidencia de la corrida de **Entrega 1**. La implementación posterior de la capa PL/SQL se documenta por separado en el [resultado de Entrega 2](../entrega2/resultado_validacion.md); sus pruebas no se atribuyen retrospectivamente a esta corrida.

La evidencia final está en [`evidencias/entrega1/2026-10-22_114219`](../../evidencias/entrega1/2026-10-22_114219/). El [resultado estructurado](../../evidencias/entrega1/2026-10-22_114219/resultado.json) contiene `status: PASS`, los identificadores de los casos, las versiones y los hashes SHA-256 del código ejecutado.

## Entorno observado

| Elemento | Valor registrado |
|---|---|
| Sistema | Windows 11, compilación 26200 |
| Base de datos | Oracle Database XE 21c, versión 21.3.0.0.0 |
| Cliente de scripts | SQL*Plus 21.3 |
| Segundo cliente | Python 3.14.5 con `python-oracledb` 26.0.1 y bibliotecas Oracle 21.3 |
| Servicio y PDB | `localhost:1521/xepdb1`, `XEPDB1` |
| Esquemas de validación final | `TURISMOUQ_E1_QA`, `TURISMOUQ_E1_QA_REPRO`, `TURISMOUQ_E1_QA_TEST` |
| Esquema para el usuario | `TURISMOUQ_E1`, con equivalencia comprobada frente a `TURISMOUQ_E1_QA` |
| Semilla | `20262` |
| Referencia temporal de carga | `2026-10-22 12:00:00 America/Bogota` |
| Base Git de los cambios | `864e13ca48df1425bfa12b4020eec5028c27e25d` |

El commit indicado es la base del trabajo. Los cambios de esta corrección se identifican por los hashes SHA-256 de archivos ejecutables registrados en `resultado.json`; no se atribuye el código corregido al commit original. SQLcl local presentó un fallo de clase principal; no se acredita ejecución con SQLcl ni con Debian.

## Pruebas funcionales aprobadas

| Casos | Comprobación observada |
|---|---|
| `I01`, `I02` | El verificador rechazó tarifa faltante, capacidad excedida, temporadas superpuestas y reservas solapadas; aceptó límites de reservas contiguas. |
| `P01` a `P04` | Rango inclusivo y de un solo día, rechazo de parámetros nulos/formato/fecha/rango inválidos y resultados equivalentes con binds desde SQL*Plus y Python. |
| `H01` a `H03` | Distribución por temporada según precios contratados, invariancia del ingreso histórico al cambiar el catálogo y presentación explícita de importes sin desglose histórico. |
| `O01` a `O05` | Estadía de 367 noches, checkout excluido, porcentaje municipal ponderado, alojamientos y meses sin reservas e inventario cero con porcentaje `NULL`. |
| `L01`, `L02` | LAG sobre calendario continuo, mes conocido sin ingreso y comparación con el mismo mes del año anterior; divisiones indefinidas conservadas como `NULL`. |
| `R01`, `R02` | Subtotales ROLLUP conciliados y ranking que conserva empates. |
| `U01`, `U02` | Composición de hospedaje/servicios con UNPIVOT, incluido total cero. |
| `N01`, `N02` | Clasificación por temporada del check-in y porcentaje de cancelación. |
| `M01` | MV desfasada antes de refrescar y concordante con la fuente después de un refresco completo; limpieza de datos de prueba comprobada. |

Las ocho consultas se ejecutaron mediante el lanzador SQL*Plus. La estructura se instaló en esquemas nuevos; la migración se probó tanto al faltar la tabla de tramos como al existir ya, sin reconstruir importes históricos.

El perfil de calendario también pasó: una sesión inicial `PERSIAN` terminó usando `GREGORIAN` y ejecutó las ocho consultas. Las dos cargas de reproducción empezaron con `GREGORIAN` y `PERSIAN` y produjeron datos idénticos después de la normalización explícita. Este resultado verifica el cierre de la dependencia del calendario de sesión; no suma un identificador adicional a los 23 casos funcionales anteriores.

## Datos obtenidos en la carga corregida

Estos valores proceden de [la instantánea de datos de la corrida final](../../evidencias/entrega1/2026-10-22_114219/data_main.json), no de estimaciones ni de los mínimos escritos en el código:

| Tabla | Filas |
|---|---:|
| `MUNICIPIO` | 12 |
| `ALOJAMIENTO` | 60 |
| `HABITACION` | 400 |
| `CLIENTE` | 3.000 |
| `RESERVA` | 25.000 |
| `RESERVA_HABITACION` | 30.973 |
| `RESERVA_HABITACION_TARIFA_APLICADA` | 32.993 |
| `RESERVA_SERVICIO` | 42.735 |
| `TEMPORADA` | 31 |
| `TARIFA` | 12.400 |

La comparación de las [dos cargas](../../evidencias/entrega1/2026-10-22_114219/data_repro.json) obtuvo igualdad de filas y hashes en las **22 tablas**. La comparación del esquema original [antes](../../evidencias/entrega1/2026-10-22_114219/original_before.json) y [después](../../evidencias/entrega1/2026-10-22_114219/original_after.json) obtuvo igualdad en sus **21 tablas**. La carga usa una referencia temporal fija; repetirla sobre un esquema ya poblado se rechaza.

## Equivalencia del esquema para el usuario

La [comparación final de entrega](../../evidencias/entrega1/2026-10-22_114219/equivalencia_esquema_entrega.json) obtuvo `PASS` entre `TURISMOUQ_E1` y `TURISMOUQ_E1_QA`:

- Mismas filas y hashes en las 22 tablas del modelo.
- Definiciones idénticas de las cuatro vistas de apoyo.
- Definición idéntica de la vista materializada.
- Las 2.220 filas de la materializada son idénticas.

La corrida QA usa sus propios esquemas aislados. El usuario puede seguir trabajando con `TURISMOUQ_E1` sin reinstalar ni regenerar su carga.

## Evidencia navegable

- [Resultado general y 23 casos](../../evidencias/entrega1/2026-10-22_114219/resultado.json).
- [Resultados de pruebas de consultas](../../evidencias/entrega1/2026-10-22_114219/pruebas_consultas.json).
- [Salida de las ocho consultas en SQL*Plus](../../evidencias/entrega1/2026-10-22_114219/ocho_consultas_sqlplus.log).
- [Verificación final de estructura y datos](../../evidencias/entrega1/2026-10-22_114219/verificacion_final.log).
- [Contraste de parámetros desde el segundo cliente](../../evidencias/entrega1/2026-10-22_114219/parametros_segundo_cliente.log).
- [Migración desde estructura previa](../../evidencias/entrega1/2026-10-22_114219/migracion_legacy_vacio.log) y [repetición idempotente](../../evidencias/entrega1/2026-10-22_114219/migracion_idempotente.log).
- [Equivalencia del esquema de entrega](../../evidencias/entrega1/2026-10-22_114219/equivalencia_esquema_entrega.json).

## Uso del esquema y límites

El esquema para el usuario es **`TURISMOUQ_E1`**. El original **`TURISMOUQ`** se mantiene. Los esquemas de reproducción y pruebas son independientes; no deben utilizarse como sustituto del esquema de entrega. Para elegir la contraseña local y ejecutar informes, seguir [EMPEZAR_AQUI.md](../../EMPEZAR_AQUI.md).

No volver a ejecutar el DDL ni la carga sobre `TURISMOUQ_E1`. Los informes posteriores necesitan conexión, verificador, refresco explícito y ocho lecturas. La MV usa `COMPLETE ON DEMAND`; no hay job diario instalado.

La ocupación representa reservas no canceladas sobre inventario bruto actual. Los ingresos representan importes contratados, incluidos pendientes y futuros; no pagos cobrados. La consulta mensual asigna todo el ingreso al mes del check-in. Estos límites se conservan en el [contrato analítico](contrato_analitico.md).

Las bases anteriores sin precios originales por tramo conservan sus totales como `SIN DESGLOSE HISTORICO`; el verificador no las certifica hasta contar con evidencia y conciliación. La migración no inventa el precio antiguo desde el catálogo actual.

**Estado histórico al cerrar esta corrida de Entrega 1:** la función de estadía, el procedimiento de reserva, el cursor parametrizado, el paquete y los disparadores de Entrega 2 estaban pendientes; las tablas de auditoría y liquidación aportaban solamente soporte estructural.

**Estado posterior:** la capa PL/SQL se implementó y se probó en esquemas aislados. La corrida E2 `2026-10-22_123445` aprobó 40 casos, 23 de regresión E1 y las ocho consultas. El [informe actual de Entrega 2](../entrega2/resultado_validacion.md) identifica su código, entorno, resultados y límites. Los registros originales de la corrida E1 se conservan como evidencia histórica.
