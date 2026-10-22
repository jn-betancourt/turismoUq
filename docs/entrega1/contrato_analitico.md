# Contrato analítico de Entrega 1

Este documento fija qué calcula cada consulta y qué evidencia permite aceptar sus resultados. El modelo mantiene la estructura de reservas previa y agrega `RESERVA_HABITACION_TARIFA_APLICADA`; no redefine pagos, disponibilidad operativa ni reglas de Entrega 2.

## Población y tiempos

- **Reserva no cancelada:** `estado <> 'CANCELADA'`. Incluye `PENDIENTE`, `CONFIRMADA`, `CHECKED_IN` y `FINALIZADA`, incluso reservas futuras. No equivale a una estancia realizada ni a un pago aprobado.
- **Estadía:** intervalo `[fecha_checkin, fecha_checkout)`. El checkout no cuenta como noche. Las validaciones de los informes comprueban datos de día completo; no se ha endurecido el contrato de horas de la cabecera en el DDL.
- **Calendario de informes:** meses entre los extremos de temporadas y las noches de las reservas. Incluye meses conocidos sin actividad; fuera de ese horizonte no se inventan ingresos u ocupación cero. No hay un límite fijo de 366 noches para descomponer una estadía.
- **Ingreso contratado:** importes guardados de hospedaje más servicios, excluyendo reservas canceladas. No se calcula a partir de pagos ni se condiciona a cobros.
- **Asignación mensual de ingreso total:** mes del check-in, por el importe completo de la reserva. No es un devengo noche a noche ni un flujo de caja.

## Calendario de la sesión

Las lecturas del proyecto requieren `NLS_CALENDAR = 'GREGORIAN'` en la misma conexión que ejecuta los SELECT. Oracle define los meses de `ADD_MONTHS` mediante ese parámetro, mientras que `TRUNC(date)` aplica reglas gregorianas independientemente de él. Mezclar ambas funciones con otro calendario puede cambiar los límites mensuales y sus denominadores. [Oracle: ADD_MONTHS](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/ADD_MONTHS.html); [Oracle: TRUNC(date)](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/TRUNC-date.html).

`02_carga.sql`, `03_consultas_analisis.sql`, `scripts/preparar_analitica.sql`, `scripts/refrescar_ocupacion.sql` y el lanzador SQL*Plus de consulta 5 fijan ese calendario al entrar. El bloque `scripts/validar_parametros_consulta.sql` también lo establece antes de convertir las fechas. Esta configuración pertenece a la sesión; no cambia el calendario global de Oracle ni se conserva automáticamente al abrir otra conexión.

Para ejecutar un SELECT suelto mediante una interfaz gráfica o un driver, ejecutar primero `ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN'` en esa misma conexión. Puede comprobarse su valor en `NLS_SESSION_PARAMETERS`, filtrando `PARAMETER = 'NLS_CALENDAR'`. Si el cliente reconecta o cambia de conexión, repetir la configuración; fijarla únicamente durante la creación de una vista no protege sus lecturas posteriores.

## Ocupación sobre inventario bruto actual

La ocupación es la suma de noches de habitación de reservas no canceladas que intersectan cada mes. La capacidad es el número **actual** de habitaciones de cada alojamiento multiplicado por los días del mes. El denominador incluye habitaciones en mantenimiento o fuera de servicio y no mantiene un historial de aperturas o cierres.

El porcentaje municipal se calcula como `100 × suma de noches reservadas / suma de capacidad`, no como promedio de porcentajes de alojamientos. El calendario incluye alojamientos con cero reservas: con inventario positivo, su ocupación es cero; con inventario cero, el porcentaje es `NULL` por falta de denominador.

Esta métrica conserva el alcance del análisis original: ocupación reservada sobre inventario bruto. No representa ocupación efectiva ni disponibilidad comercial de cada fecha. Cambios posteriores del inventario o de las dimensiones de alojamiento pueden cambiar la presentación de períodos anteriores; esas dimensiones no se congelan en esta corrección.

## Precio contratado y procedencia histórica

Cada tramo de `RESERVA_HABITACION_TARIFA_APLICADA` conserva una habitación de una reserva, un intervalo de noches `[fecha_inicio_tramo, fecha_fin_tramo)`, una referencia a temporada, el tipo de temporada aplicado y el precio por noche aplicado. El tipo y precio guardados se usan en el análisis de ingresos por temporada, aunque el catálogo se modifique después.

| Origen | Significado | Evidencia |
|---|---|---|
| `CAPTURADO` | Precio guardado cuando se generó o contrató la estadía. En la carga del proyecto son datos sintéticos capturados durante su generación. | Referencia opcional; no convierte datos sintéticos en transacciones reales. |
| `RECONSTRUIDO_VALIDADO` | Precio antiguo recuperado mediante soporte verificable y conciliado. | `referencia_evidencia` obligatoria y no vacía. |

La PK y los CHECK controlan cada fila. La aceptación del conjunto requiere:

1. Tramos contenidos en la estadía y fechas sin hora.
2. Cobertura completa de las noches de cada detalle de habitación.
3. Ausencia de solapamientos y duplicaciones.
4. Conciliación de la suma de `noches × precio aplicado` con `precio_estadia_habitacion`.
5. Procedencia y evidencia válidas.

La igualdad con un total antiguo después de sumar tarifas **actuales** no demuestra qué precios se contrataron. La migración agrega estructura, conserva los valores originales y no rellena estos tramos automáticamente.

Cuando un detalle no tiene ningún tramo, su total guardado se presenta como **`SIN DESGLOSE HISTORICO`**, con importe y cantidad de detalles sin desglose. No se asigna artificialmente a una temporada. Si hay tramos parciales, el conjunto tampoco pasa la validación; el informe no debe certificarse por la sola presencia de filas en la vista.

`scripts/verificar_entrega1.sql` rechaza datos sin cobertura o sin conciliación. Un análisis parcial de una base antigua puede conservar información útil, pero no acredita el cumplimiento completo de la entrega.

## Las ocho consultas

| N.º | Archivo | Métrica y alcance |
|---|---|---|
| 1 | `consultas/01_ocupacion_municipio_mes.sql` | PIVOT de ocupación bruta por municipio, año y mes. Usa el calendario completo y conserva meses de actividad cero. |
| 2 | `consultas/02_ingresos_temporada.sql` | Hospedaje contratado por municipio, tipo de alojamiento y tipo de temporada aplicado. ROLLUP y GROUPING distinguen subtotales. Excluye servicios; conserva importes sin evidencia como `SIN DESGLOSE HISTORICO`. |
| 3 | `consultas/03_top_alojamientos.sql` | Ranking de ingreso contratado total, hospedaje más servicios, dentro de cada municipio. `RANK` conserva empates; `puesto <= 3` puede producir más de tres filas. Los alojamientos sin reservas no aparecen como candidatos con ingreso cero. |
| 4 | `consultas/04_variacion_ingresos.sql` | Ingreso total por mes del check-in, variación mensual con LAG y comparación con el mismo mes del año anterior. Completa meses conocidos antes de aplicar el filtro de presentación. |
| 5 | `consultas/05_consulta_parametrizada.sql` | Reservas cuyo check-in cae dentro del rango inclusivo de fechas: cantidad, ingreso total, ticket promedio y noches promedio por alojamiento. Un rango igual de inicio y fin es válido. |
| 6 | `consultas/06_ocupacion_materializada.sql` | Lectura gerencial de la MV para alojamientos con ocupación bruta inferior al 30 %. El ejemplo usa diciembre de 2025 e incluye alojamientos con 0 %. |
| 7 | `consultas/07_composicion_ingresos.sql` | UNPIVOT de hospedaje y servicios por municipio y año del check-in, con participación sobre su ingreso total. |
| 8 | `consultas/08_anticipacion_cancelaciones.sql` | Anticipación, duración y cancelaciones según la temporada del check-in. Incluye canceladas deliberadamente; clasifica por el calendario de temporadas, no por el tipo de precio congelado de la consulta 2. |

En la consulta 4, si el mes anterior no pertenece al horizonte conocido, su ingreso anterior y la variación son `NULL`; si el denominador anterior es cero, la variación porcentual también es `NULL`. No se sustituye una variación indefinida por cero. La misma regla de denominador se aplica a la composición porcentual de la consulta 7.

Los ingresos de las consultas 3, 4, 5 y 7 se atribuyen al alojamiento de la cabecera. La ocupación y los tramos por temporada se vinculan a la habitación. Se mantiene `reserva.id_alojamiento` nullable en el modelo previo; la aceptación de los datos de entrega comprueba coherencia entre cabecera y detalles. No se introduce una nueva regla de reserva con varios alojamientos.

## Parámetros y clientes

El SELECT canónico de consulta 5 contiene solamente SQL y dos binds de texto: `:fecha_ini` y `:fecha_fin`. El formato admitido es estrictamente `YYYY-MM-DD`; ambas fechas deben existir y el inicio debe ser anterior o igual al final. La fecha final `9999-12-31` se rechaza porque el filtro requiere su día siguiente.

`scripts/validar_parametros_consulta.sql` valida esos valores sin modificarlos. Debe ejecutarse con los mismos binds y en la misma conexión que el SELECT. En SQL*Plus, `scripts/ejecutar_consulta_parametrizada_sqlplus.sql` declara e inicializa ambos binds, ejecuta la validación y después el SELECT. Sus valores predeterminados son junio y julio de 2025. Ejecutarlo de nuevo restablece esos valores; para conservar otros binds hay que ejecutar la validación y el SELECT directamente.

`SET DEFINE OFF` controla sustituciones de SQL*Plus, no elimina los binds. Otro cliente debe suministrar ambos valores con su mecanismo de parámetros; los comandos `VARIABLE`, `PRINT` y el terminador `/` de scripts no son sentencias para enviar al motor mediante un driver.

La ejecución manual de los lanzadores SQL*Plus requiere que la raíz del repositorio sea su directorio de trabajo. En CMD se ejecuta primero `cd /d C:\Users\ASUS\Desktop\U_SEM7-8\BD_2\tourism\turismoUq` y después se abre SQL*Plus. Las rutas `@` de las consultas se resuelven bajo ese requisito; no se acredita ejecución desde cualquier directorio. El ejecutor Python fija esa raíz como directorio de trabajo de sus procesos SQL*Plus.

El calendario de sesión requerido es `GREGORIAN`. Los puntos de entrada lo fijan explícitamente; al ejecutar un SELECT independiente, el cliente también debe establecerlo. Así se evita que `ADD_MONTHS` y `MONTHS_BETWEEN` usen un calendario distinto al de los límites mensuales construidos con `TRUNC`.

## Vista materializada y actualización

`MV_OCUPACION_MENSUAL` usa `BUILD IMMEDIATE` y `REFRESH COMPLETE ON DEMAND`. La construcción inicial obtiene una instantánea; los cambios siguientes en reservas o inventario requieren refrescarla explícitamente con `scripts/refrescar_ocupacion.sql` antes de generar evidencia.

La política acepta desfase entre refrescos. `COMPLETE` evita depender de las condiciones de refresco rápido para un calendario generado con uniones y agregaciones; `ON DEMAND` separa el costo del refresco de cada confirmación de datos operativos. No se instala ni se promete un job diario, una actualización en tiempo real o una mejora de rendimiento sin medición.

El reporte debe conservar `last_refresh_date`, `last_refresh_type`, `staleness` y el estado de compilación, junto con los resultados. El refresco es una operación de escritura y debe realizarse en una sesión sin cambios pendientes.

## Ejecución y certificación

La secuencia de una instalación nueva es: infraestructura, propietario con cuotas y privilegios, DDL, carga, verificación, preparación de objetos, refresco y ocho lecturas. En una base anterior se sustituye DDL/carga por la migración estructural y la acreditación de los tramos; no se regeneran reservas.

La carga configura únicamente `carga_semilla` y `carga_referencia` mediante sus dos `DEFINE`. La referencia incluye una región horaria y controla la clasificación de estados. Las comparaciones de reproducción requieren el mismo código, configuración y versión de Oracle, además de esquemas aislados y vacíos.

El ejecutor local se consulta con `python tests/validar_local.py --help`, desde la raíz del repositorio. Requiere `oracledb==26.0.1`, declarado en `tests/requirements.txt`, y acepta dependencias locales en `.validation-deps`. Sus opciones reales de esquema, servicio, PDB, SQL*Plus, bibliotecas Oracle y esquema preservado están descritas en el [README](../../README.md#validación-y-evidencia).

El [informe de validación](resultado_validacion.md) separa compilación, integridad, volúmenes, consultas, invariancia frente a cambios del catálogo, reproducción y clientes realmente probados. La corrida final ejecutó SQL*Plus y `python-oracledb` 26.0.1; SQLcl local y Debian no se presentan como entornos probados.

La evidencia final debe referir el código y entorno ejecutados. La existencia del DDL, de esta documentación o de una salida parcial no sustituye una ejecución satisfactoria ni acredita los componentes pendientes de Entrega 2.
