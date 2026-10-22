# Plan del incremento de Entrega 2: capa PL/SQL

Fecha: 22 de octubre de 2026. **Estado: planificación; la capa PL/SQL todavía no está implementada.**

Base: correcciones de Entrega 1, commit `06f5bd452ab22143ceb4f7a7760248ac5137f85d`, incorporadas mediante el [PR #1](https://github.com/jn-betancourt/turismoUq/pull/1). La [validación de Entrega 1](../entrega1/resultado_validacion.md) aprobó ocho consultas y 23 casos. Esos resultados no acreditan ninguna función, procedimiento o trigger de Entrega 2.

## 1. Resultado esperado y alcance

Entregar un paquete compilado en Oracle XE 21c que cotice estadías, cree reservas completas y liquide un mes por alojamiento. Añadir auditoría de cambios de precio y controles de solapamiento compatibles con el modelo cabecera/detalle y con dos sesiones concurrentes.

| Requisito de la entrega | Resultado propuesto | Aceptación observable |
|---|---|---|
| `fn_valor_estadia` | Función pública del paquete, con los tres parámetros exigidos | Cobra cada noche con la temporada correspondiente; detecta cobertura incompleta o ambigua. |
| `sp_crear_reserva` | Procedimiento público para una o varias habitaciones del mismo alojamiento | Cabecera, detalles, precios aplicados, servicios y total se guardan juntos; errores propios ante fechas, indisponibilidad y exceso de capacidad. |
| Cursor explícito con parámetros | Cursor nombrado dentro del cuerpo del paquete, utilizado por la liquidación mensual | Procesa varios alojamientos con el mismo corte y porcentaje; totales comprobados sin multiplicar habitaciones por servicios. |
| Todo agrupado en paquete | `pkg_turismouq`, especificación y cuerpo | Tipos, errores, función, procedimientos y rutinas compartidas en un contrato único. |
| Auditoría a nivel de sentencia | Captura por fila y persistencia en `AFTER STATEMENT` mediante trigger compuesto | Una sentencia masiva conserva todos los pares anterior/nuevo y su identidad común. Requiere validar el encaje académico descrito en la sección 4. |
| Prevención de solapes a nivel de fila | Trigger compuesto sobre detalle, con fases por fila y validación final del conjunto; control complementario sobre cabecera | Rechazo de solapes sin `ORA-04091`, también en DML masivo y cambios de fechas/estado. Requiere la misma validación académica. |

Los triggers son objetos externos del esquema; Oracle no permite declararlos dentro del cuerpo de un paquete. Sus reglas reutilizables sí pertenecerán al paquete. No se crearán funciones independientes duplicadas solo para imitar los nombres de la rúbrica. [Oracle: paquetes](https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/plsql-packages.html).

Quedan fuera: frontend o API, cobro de pagos, dispersión de dinero, devoluciones, purga histórica, cambios generales de reservas ya creadas, recálculo contable automático y auditoría de INSERT/DELETE de TARIFA. Tampoco se instalará un job de liquidación ni de refresco de ocupación.

## 2. Punto de partida comprobado

El [DDL actual](../../01_DDL_TURISMOUQ_ORACLE21C.sql) contiene 22 tablas:

- `RESERVA` guarda fechas y estado; `RESERVA_HABITACION` permite varias habitaciones y personas por habitación. La capacidad se obtiene de `TIPO_HABITACION.capacidad_estandar`.
- `TEMPORADA.fecha_fin` es inclusiva. `TARIFA` tiene unicidad habitación/temporada y precio positivo, pero el DDL no garantiza que las temporadas cubran todas las noches sin huecos o superposiciones.
- `RESERVA_HABITACION_TARIFA_APLICADA` ya conserva tramos y precios contratados. No hace falta una segunda tabla de precios históricos.
- `AUDITORIA_TARIFA` existe sin trigger. Su usuario admite 30 caracteres y no identifica la sentencia que originó un grupo de cambios.
- `LIQUIDACION_MENSUAL` tiene unicidad alojamiento/año/mes y estados `CALCULADA`, `DISPERSADA`, `PAGADA`; no conserva porcentaje ni criterio de comisión.
- El aprovisionamiento de Entrega 1 no concede `CREATE PROCEDURE` ni `CREATE TRIGGER`.
- El verificador de Entrega 1 detecta solapes entre todos los estados. Esa regla debe evolucionar conscientemente para permitir reutilizar noches canceladas.

El esquema original `TURISMOUQ` y el corregido `TURISMOUQ_E1` se conservarán. La implementación y las primeras pruebas se harán en **un esquema nuevo `TURISMOUQ_E2`** y otro esquema vacío de fixtures; si esos nombres ya existen, se elegirá otro prefijo sin borrar cuentas.

## 3. Reglas confirmadas y decisiones propuestas

Las siguientes cuatro reglas fueron confirmadas expresamente por el usuario durante esta planificación:

| Regla confirmada | Contrato para Entrega 2 |
|---|---|
| Población de liquidación | Solo reservas `FINALIZADA`, por el mes de su checkout. Se incluye el importe completo de la reserva. |
| Comisión | Porcentaje recibido como parámetro sobre hospedaje más servicios; sin porcentaje fijo ni predeterminado. |
| Auditoría | Solo cambios de `TARIFA.precio_noche` mediante UPDATE, conservando precio anterior y nuevo. |
| Inventario | `CANCELADA` libera las noches. `PENDIENTE`, `CONFIRMADA`, `CHECKED_IN` y `FINALIZADA` bloquean sus respectivos intervalos. |

La liquidación **no equivale** al informe de ingresos de Entrega 1: este conserva estados no cancelados y mes del check-in. Las dos métricas deben seguir nombradas y probadas por separado.

Para concretar el incremento se proponen estas decisiones de implementación; no se presentan como requisitos previamente aprobados:

| Decisión propuesta | Motivo y límite |
|---|---|
| Reserva nueva en `PENDIENTE` | Reutiliza el valor predeterminado del DDL. Ese estado ya bloquea por decisión confirmada. |
| Una reserva, un alojamiento y varias habitaciones | Respeta el modelo N:M existente; no permite mezclar establecimientos en la misma cabecera. |
| Servicios opcionales al crear la reserva | Permite completar el contrato que ya representa `RESERVA_SERVICIO`; sin servicios, su importe es cero. |
| Fechas de día completo; rechazar horas | Conserva el contrato de tramos diarios de Entrega 1. No truncar silenciosamente una entrada. No añadir una prohibición nueva de reservas retroactivas. |
| Sin liquidación nueva para alojamiento sin reservas elegibles | No crea filas nuevas sin actividad; sí revisa cortes existentes que perdieron toda su población. |
| Repetición idéntica sin cambios; diferencias rechazadas | Evita sobrescribir un corte previo. El recálculo explícito será otra operación futura. |
| Espera de bloqueo acotada, inicialmente cinco segundos | Un bloqueo ocupado devuelve conflicto temporal; no se interpreta como inexistencia ni indisponibilidad definitiva. El valor se centraliza y se prueba. |
| Aislamiento soportado `READ COMMITTED` | Se comprueba la disponibilidad mediante una consulta nueva después de adquirir los bloqueos. No se promete soporte de `SERIALIZABLE` sin sus pruebas específicas. |

Antes de implementar cada componente se revisarán sus propuestas aplicables. La decisión académica de la sección siguiente condiciona los triggers; no impide avanzar con función, reserva o liquidación una vez autorizada su implementación. No se añaden restricciones nuevas sobre estados de clientes o alojamientos sin acordarlas; sí se validan referencias y el estado operativo de cada habitación solicitado por la reserva.

## 4. Decisión técnica que debe cerrarse con la rúbrica

Un trigger simple de sentencia no dispone de `:OLD` y `:NEW` para cada fila. Un trigger de fila sobre `RESERVA_HABITACION` tampoco debe consultar esa misma tabla mientras se modifica. Oracle ofrece triggers compuestos con fases por fila y por sentencia para resolver esas necesidades. [Oracle: triggers y restricciones de tabla mutante](https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/plsql-triggers.html).

**Diseño recomendado:** auditoría que escribe en `AFTER STATEMENT` después de capturar los pares por fila, y prevención de solapes que recoge los cambios por fila y valida el conjunto al terminar la sentencia.

Antes de dar por satisfechos los rótulos académicos «nivel de sentencia» y «nivel de fila», mostrar al docente ese diseño y confirmar que acepta las fases de un trigger compuesto. La validación del conjunto no debe presentarse como si ocurriera exclusivamente en un trigger simple `FOR EACH ROW`.

Si exige literalmente dos triggers simples con la comprobación del solape enteramente por fila, detener ese diseño y acordar una alternativa estructural, por ejemplo una tabla de ocupación por noche con unicidad habitación/noche. Esa alternativa ampliaría modelo, migración y volumen, y **no forma parte del diseño inicial**. No resolverlo escondiendo la consulta de la tabla mutante dentro de una función o vista.

## 5. Contrato propuesto del paquete

Nombre: **`pkg_turismouq`**, con `AUTHID DEFINER`, tipos públicos de solicitud, constantes de error, función de cotización y procedimientos de reserva y liquidación. La especificación pública no expondrá una rutina que permita insertar auditorías arbitrarias.

Las firmas se describen como contrato, no como código compilado:

| Operación | Entradas | Salidas |
|---|---|---|
| `fn_valor_estadia` | `p_id_habitacion NUMBER`, `p_fecha_in DATE`, `p_fecha_out DATE` | `NUMBER`, importe de hospedaje con dos decimales. |
| `sp_crear_reserva` | Cliente, alojamiento, fechas, colección de habitaciones/personas y colección opcional de servicios/cantidades | ID de reserva y valor total mediante parámetros OUT. |
| `sp_liquidar_mes` | Año, mes, porcentaje de comisión obligatorio y filtro opcional de alojamiento | Cantidad de liquidaciones nuevas y cantidad de cortes idénticos conservados. |

Las colecciones de habitaciones y servicios se declararán en la especificación como registros y tablas PL/SQL, con nombres completos como `tipo_solicitud_habitacion` y `lista_solicitudes_habitacion`. El contrato inicial admite invocación desde PL/SQL y el ejecutor de pruebas; no se promete compatibilidad automática de esas colecciones con cualquier driver o con una API inexistente.

Parámetros concretos propuestos para los procedimientos:

| Operación | Parámetros y tipos |
|---|---|
| Reserva, entradas | `p_id_cliente NUMBER`, `p_id_alojamiento NUMBER`, `p_fecha_in DATE`, `p_fecha_out DATE`, `p_habitaciones lista_solicitudes_habitacion`, `p_servicios lista_solicitudes_servicio` —colección vacía si no se solicitan servicios—. |
| Reserva, salidas | `p_id_reserva OUT NUMBER`, `p_valor_total OUT NUMBER`. |
| Liquidación, entradas | `p_anio NUMBER`, `p_mes NUMBER`, `p_porcentaje_comision NUMBER`, `p_id_alojamiento NUMBER DEFAULT NULL`. |
| Liquidación, salidas | `p_liquidaciones_creadas OUT PLS_INTEGER`, `p_liquidaciones_conservadas OUT PLS_INTEGER`. |

Las salidas solo son válidas si el procedimiento regresa sin excepción. No se usará `NOCOPY` ni se prometerá un valor de salida concreto después de un error.

Habrá una rutina privada que **lea y valide tramos una vez por habitación**, devolviendo tramos e importe juntos. La función devuelve su suma; el procedimiento persiste esa misma captura. No llamar a la función y volver a leer TARIFA para reconstruir los precios guardados: dos consultas separadas pueden observar cambios de catálogo diferentes. Esta coherencia se garantiza por captura de habitación, sin prometer una instantánea global común a todas las habitaciones. [Oracle: consistencia de lectura](https://docs.oracle.com/en/database/oracle/oracle-database/21/cncpt/data-concurrency-and-consistency.html).

Los validadores compartidos que los triggers necesiten invocar serán subprogramas visibles, sin controles de transacción y sin funciones de escritura arbitraria. La cotización interna y la captura de tramos seguirán privadas. No se usará estado global de sesión para transportar cambios entre triggers.

## 6. Función `fn_valor_estadia`

Representa una **cotización con el catálogo actual**, no la recuperación del precio de una reserva antigua. La disponibilidad y la capacidad pertenecen al procedimiento de reserva.

Algoritmo previsto:

1. Validar habitación y fechas no nulas, fechas sin hora y `fecha_out > fecha_in`.
2. Comprobar existencia de la habitación.
3. Leer en una sola consulta las temporadas que intersectan `[fecha_in, fecha_out)`, con su tarifa para la habitación. Usar unión externa para poder diagnosticar una tarifa faltante.
4. Comprobar también que los límites de las temporadas participantes no contienen horas. Convertir cada temporada inclusiva a un intervalo equivalente con fin exclusivo; controlar el extremo máximo de DATE para no desbordar al sumar un día.
5. Ordenar por inicio e identificador; recortar cada tramo a la estadía. Mantener un extremo esperado: inicio mayor al esperado significa hueco; menor significa solapamiento; igual permite continuar.
6. Exigir tarifa en cada tramo, precio positivo y cobertura hasta el checkout. No basta con comparar la suma de noches: un hueco y una superposición podrían compensarse.
7. Acumular `noches × precio_noche`, con aritmética NUMBER y límites compatibles con `NUMBER(12,2)`. Devolver el importe a dos decimales.

No habrá precio cero como reemplazo, selección arbitraria de una temporada ni límite de 366 noches. No escribirá tablas, no hará COMMIT y no se declarará `DETERMINISTIC` ni usará caché de resultados en este incremento.

Caso de referencia: entrada 29/06/2025 y salida 03/07/2025, con junio a 100 y julio a 150, produce dos noches por tramo: `200 + 300 = 500`. Tras cambiar junio a 120, una nueva cotización da 540; el contrato anterior conserva 500.

## 7. Procedimiento `sp_crear_reserva`

Secuencia propuesta, como una sola unidad de trabajo:

1. Inicializar las salidas y establecer un savepoint propio antes de cualquier escritura de la llamada.
2. Validar primero fechas no nulas, sin hora y checkout posterior al check-in, antes de consultar disponibilidad. Después validar cliente y alojamiento existentes; colección de habitaciones no vacía, identificadores sin duplicados y personas enteras positivas. Validar servicios/cantidades con las mismas reglas de integridad.
3. Bloquear las filas de las habitaciones solicitadas en orden ascendente de ID. Comprobar que pertenecen al alojamiento y están `DISPONIBLE`.
4. Consultar conflictos **después** de obtener los bloqueos. Solo cuentan reservas no canceladas, con `nuevo_inicio < checkout_existente AND checkin_existente < nuevo_fin`. La igualdad entre salida y siguiente entrada permite contigüidad.
5. Validar por habitación `personas_hospedadas <= capacidad_estandar`; una capacidad total suficiente no compensa el exceso de una habitación.
6. Obtener los tramos e importe por habitación con la rutina privada. Capturar también el precio vigente de los servicios solicitados del mismo alojamiento; el llamador no suministra precios.
7. Crear la cabecera en estado propuesto `PENDIENTE` y obtener su identidad con RETURNING. Insertar detalles, tramos `CAPTURADO` y servicios; sumar los precios almacenados y comprobar el límite de `valor_total`.
8. Devolver ID y total. No registrar pagos, no cambiar la habitación a un estado global «ocupada» y no refrescar la MV dentro de la reserva.
9. Ante fallo, revertir al savepoint de la llamada y propagar el error. Las salidas no se consideran válidas. Conservar el trabajo previo de la sesión y no hacer COMMIT interno.

Los bloqueos de habitación se mantienen hasta que el llamador confirme o revierta la transacción. Bloquear únicamente reservas existentes deja desprotegido el caso de una habitación todavía sin reservas. `SELECT FOR UPDATE` proporciona el recurso común; la consulta posterior decide el conflicto. [Oracle: bloqueo manual](https://docs.oracle.com/en/database/oracle/oracle-database/21/cncpt/data-concurrency-and-consistency.html).

Un timeout de bloqueo tendrá error propio de conflicto temporal. Un deadlock o un error técnico inesperado se propagará con su causa; no se convertirá cualquier excepción en «habitación no disponible».

## 8. Triggers: responsabilidad, momento y cobertura

### 8.1 Auditoría de precio de TARIFA

Trigger compuesto para UPDATE de `precio_noche`:

- Antes de la sentencia, obtener un identificador `SYS_GUID`, `SESSION_USER` y una marca temporal UTC comunes. Documentar UTC para los eventos nuevos, sin reinterpretar timestamps legados de zona desconocida.
- En la fase por fila, recopilar ID de tarifa, precio anterior y nuevo únicamente si el importe cambió.
- En `AFTER STATEMENT`, insertar el lote en `AUDITORIA_TARIFA`; usar estado local al trigger y una inserción de conjunto adecuada al tamaño probado.
- UPDATE sin cambio efectivo o que afecte cero filas produce cero eventos.
- La auditoría participa de la misma transacción. Un ROLLBACK o una sentencia fallida no conserva eventos como cambios confirmados.

`SESSION_USER` identifica la conexión; no sustituirlo por la identidad de ejecución del paquete. No habrá transacción autónoma, COMMIT ni modificación de precios contratados. INSERT, DELETE y cambios de otros campos de TARIFA quedan fuera del alcance confirmado.

### 8.2 Solapamientos sobre detalle y cabecera

Trigger compuesto sobre INSERT/UPDATE relevantes de `RESERVA_HABITACION`:

- Las fases por fila recogen las reservas y las habitaciones anteriores/nuevas afectadas.
- Al terminar la sentencia, deduplicar y bloquear primero las cabeceras afectadas —IDs anteriores y nuevos, en orden— y después sus habitaciones ordenadas. Abrir una consulta nueva para releer fechas/estado y comprobar todos los conflictos del conjunto, incluida la colisión entre filas de la misma sentencia.
- Excluir la misma reserva de su comparación y aplicar la población no cancelada confirmada.
- Ante conflicto, lanzar el error propio; no corregir ni borrar filas automáticamente.

Un control complementario sobre UPDATE de `RESERVA.fecha_checkin`, `fecha_checkout` o `estado` debe recoger sus IDs por fila y validar en la fase de sentencia, incluidas sus habitaciones. Cubre la reactivación de una cancelada y el cambio de fechas que provocarían un cruce. Para operaciones controladas sobre reservas existentes, el orden será cabecera y después habitaciones ordenadas.

El bloqueo compartido de cabecera también evita que una inserción de detalle no confirmada pase inadvertida para otra sesión que cambia sus fechas. La creación de una reserva nueva puede bloquear habitaciones antes de insertar su cabecera: ese ID nuevo todavía no es visible a otras sesiones. Los cambios sobre cabeceras ya existentes siempre respetarán el orden anterior.

Estos controles resuelven la consulta de la tabla mutante; el protocolo de bloqueos resuelve las sesiones concurrentes. No son garantías intercambiables. Las rutinas llamadas por triggers no usarán savepoints, COMMIT ni ROLLBACK. [Oracle: restricciones de triggers](https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/plsql-triggers.html).

La escritura operativa se hará con un usuario que tenga EXECUTE sobre el paquete y sin DML directo sobre tablas base. El propietario seguirá siendo administrativo: comprobar solapes en un UPDATE manual no equivale a recalcular coherentemente un contrato y sus tramos. No se añade en este incremento una API de modificación, cancelación o reactivación; esos cambios se ejercitan como pruebas administrativas de los controles.

## 9. Liquidación mensual mediante cursor explícito

Contrato del período: primer día del mes incluido y primer día del siguiente mes excluido, aplicados a **fecha_checkout**. Validar año/mes y el último período representable antes de calcular el límite siguiente. Usar calendario gregoriano en instalación, pruebas y ejecución.

El porcentaje es obligatorio, de 0 a 100, con hasta cuatro decimales. Por ejemplo, `12` representa 12 %, no 0,12. Ese 12 será un dato de prueba, no un valor predeterminado del negocio.

Cursor nombrado propuesto: `cursor_liquidacion_alojamiento(p_inicio, p_fin_exclusivo, p_id_alojamiento)`. Se declara y se abre/fetch/cierra explícitamente en el cuerpo del paquete; la ruta de excepción también lo cierra si permanece abierto. Los parámetros permiten reutilizar el proceso para todo el mes o un alojamiento. [Oracle: cursores explícitos](https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/static-sql.html).

Preparación y procesamiento:

1. Validar parámetros y, si existe filtro, la existencia del alojamiento. Establecer el savepoint del lote.
2. Bloquear los alojamientos objetivo en orden estable. Esta primera versión puede serializar dos períodos distintos del mismo alojamiento; se prefiere esa solución simple a añadir un gestor de locks por período.
3. Abrir el cursor después de adquirir los bloqueos. Seleccionar reservas `FINALIZADA` con checkout en el período y alojamiento coherente. La población de alojamientos a revisar es la unión de los que tienen actividad elegible y los que ya tienen corte en ese período; estos últimos deben aparecer con fuente cero si perdieron toda su actividad.
4. Agregar habitaciones por reserva y servicios por reserva **antes** de unirlos. Después agrupar por alojamiento. Leer importes contratados; no TARIFA actual, pagos ni la MV de ocupación.
5. Calcular base = hospedaje + servicios; comisión = `ROUND(base × porcentaje / 100, 2)`; neto = base − comisión. Validar límites de `NUMBER(14,2)`.
6. Si no existe corte y hay actividad, insertar `CALCULADA` con importes y metadatos de la política. Sin actividad ni corte previo, no insertar fila. Si existe corte pero la fuente quedó vacía, comparar igualmente sus importes con cero; no omitir el control.
7. Si ya existe un corte con los mismos importes, porcentaje y criterio, conservar ID, fecha y estado sin DML. Si difiere, rechazar la operación; nunca sobrescribir `DISPERSADA` o `PAGADA`.
8. Ante cualquier fallo del lote, revertir su trabajo hasta el savepoint y propagar el error. El llamador confirma todo el lote; no habrá commits por alojamiento.

La llave UNIQUE impide duplicar un período, pero el bloqueo y la comparación explícita proporcionan el comportamiento de repetición. La igualdad se comprueba sobre los resultados y metadatos almacenados; este incremento no agrega un detalle inmutable de todas las reservas que formaron el corte ni un sistema de reversos contables.

Por tanto, no se promete detectar una sustitución de reservas fuente que conserve exactamente los mismos importes y metadatos. Si se exige identidad completa de la población, se deberá ampliar el diseño con detalle o huella reproducible persistidos antes de implementar esa garantía.

Ejemplo: estadía finalizada 31/01–01/02, hospedaje 200, servicios 50 y comisión de prueba 12 %. Enero no la liquida; febrero guarda base 250, comisión 30 y neto 220.

## 10. Migraciones, permisos y compatibilidad

Cambios propuestos para la implementación, todavía sin ejecutar:

| Objeto | Cambio | Tratamiento de datos existentes |
|---|---|---|
| `AUDITORIA_TARIFA` | Ampliar `usuario_oracle` a 128 y añadir `id_sentencia RAW(16)` | Conservar eventos previos; no inventar identificadores comunes para sentencias antiguas. El trigger nuevo siempre informa el ID. |
| `LIQUIDACION_MENSUAL` | Añadir `porcentaje_comision NUMBER(7,4)`, `base_comision NUMBER(14,2)` y `criterio_liquidacion VARCHAR2(40)` | Añadir primero columnas compatibles con NULL para registros antiguos. No atribuir una tasa ni política histórica supuesta. |
| Reglas de liquidación | CHECK: porcentaje entre 0 y 100; metadatos todos desconocidos o todos informados; base = hospedaje + servicios y comisión = `ROUND(base × porcentaje / 100, 2)` para registros completos | Aceptar legado identificado por metadatos desconocidos; el procedimiento rechaza reutilizarlo hasta reconciliación explícita. Las inserciones nuevas del paquete siempre llenan los tres campos. |
| DDL y representaciones | Reflejar los mismos campos y relaciones en DDL, DBML, diagrama y entidades | La instalación nueva y la migrada tendrán un contrato compatible; no se eliminarán restricciones para hacer pasar pruebas. |
| Verificador | Aplicar solapes operativos solo a estados no cancelados | Conservar controles financieros, cobertura de tramos y mínimos de la carga. Documentar el cambio de política respecto de la evidencia E1. |
| Propietario | Verificar/conceder `CREATE PROCEDURE` y `CREATE TRIGGER` | Privilegios concretos en XEPDB1, sin `CREATE ANY` ni roles administrativos nuevos. |
| Usuario de ejecución de pruebas | CREATE SESSION y EXECUTE sobre el paquete | Sin INSERT/UPDATE/DELETE de tablas; las fixtures se preparan con el propietario aislado. |

Se actualizará el bootstrap para comprobar privilegios directos necesarios. [Oracle: CREATE PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/CREATE-PACKAGE-statement.html), [Oracle: CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/CREATE-TRIGGER.html).

La migración debe comprobar columnas, tipos y restricciones si ya existen, y detenerse ante incompatibilidades. No asignará porcentajes cero para encubrir desconocimiento. Las columnas de legado no equivalen a permiso para crear liquidaciones nuevas incompletas.

El DDL de Oracle confirma transacciones. Por eso el instalador necesitará preflight, respaldo y ejecución por etapas; no prometerá deshacer una instalación completa con un ROLLBACK final. El plan de recuperación conservará los datos y permitirá reinstalar objetos PL/SQL corregidos, sin borrar cuentas ni eliminar columnas con historia automáticamente.

## 11. Errores propios y contrato transaccional

Propuesta de rango E2, sin colisionar con los controles E1 actuales:

| Código propuesto | Condición |
|---|---|
| `-20301` | Checkout anterior o igual al check-in. |
| `-20302` | Fechas nulas, con hora o extremo no soportado. |
| `-20303` | Habitación inexistente. |
| `-20304` | Habitación no disponible por estado operativo o por solapamiento. |
| `-20305` | Capacidad de una habitación excedida. |
| `-20306` | Cliente/alojamiento inexistente o pertenencia incoherente. |
| `-20307` | Colección vacía, identificadores duplicados o cantidades/personas inválidas. |
| `-20308` | Hueco en la cobertura de temporadas. |
| `-20309` | Temporadas superpuestas para una noche. |
| `-20310` | Tarifa de habitación/temporada ausente. |
| `-20311` | Importe fuera de capacidad monetaria. |
| `-20312` | Recurso bloqueado: conflicto temporal después de la espera acotada. |
| `-20313` | Servicio inexistente o perteneciente a otro alojamiento. |
| `-20314` | Incoherencia de importes o tramos de la población procesada. |
| `-20320` | Período o porcentaje de comisión inválido. |
| `-20321` | Corte CALCULADA existente con valores distintos; requiere recálculo explícito. |
| `-20322` | Intento de alterar un corte DISPERSADA/PAGADA con valores distintos. |
| `-20323` | Corte previo sin metadatos suficientes de comisión o criterio. |

Centralizar constantes y excepciones con nombres claros; usar `RAISE_APPLICATION_ERROR` para los rechazos de dominio, y conservar la causa de errores inesperados. El código y el mensaje deben permitir distinguir las tres excepciones obligatorias de la rúbrica.

Lanzar un error por sí solo no garantiza revertir todo el DML previo de un procedimiento. Los procedimientos públicos delimitarán su trabajo con savepoint y rollback parcial, mientras los validadores usados por triggers carecerán de control transaccional. El llamador conserva la decisión final de COMMIT/ROLLBACK. [Oracle: propagación y manejo de errores](https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/plsql-error-handling.html).

## 12. Secuencia de implementación y archivos

Los siguientes nombres son **archivos propuestos**; no existen como implementación por haber escrito este plan.

| Trabajo | Dependencia | Archivos o resultado propuesto | Criterio para terminar |
|---|---|---|---|
| E2-00 Cerrar contrato | Ninguna | Este plan y consulta docente de fases de trigger | Contratos base revisados y decisión académica registrada como condición específica de E2-05. |
| E2-01 Preparar entorno y migración | Contratos base de E2-00 | `scripts/preparar_entrega2.sql`, `migraciones/002_soporte_plsql.sql`, actualización del DDL/modelo | Esquema aislado, privilegios suficientes, migración repetible y originales intactos. |
| E2-02 Definir especificación | E2-01 | `plsql/01_pkg_turismouq.pks` | Tipos, firmas, errores y contrato de transacción cerrados. |
| E2-03 Cotizar y capturar | E2-02 | Primera parte de `plsql/02_pkg_turismouq.pkb` | Función y helper pasan F01–F07, sin escritura. |
| E2-04 Crear reservas | E2-03 | Procedimiento y validadores del mismo cuerpo | Operación completa y errores propios; pruebas de rollback y concurrencia. |
| E2-05 Instalar controles | E2-04 y validación académica de fases de trigger | `plsql/03_trg_auditar_tarifa.sql`, `plsql/04_trg_reserva_habitacion.sql`, `plsql/05_trg_reserva.sql` | Auditoría masiva y protección de detalle/cabecera sin tabla mutante. |
| E2-06 Liquidar mes | E2-03 y E2-01 | Cursor y procedimiento en el cuerpo del paquete | Corte según checkout, comisión capturada, repetición y dos sesiones comprobadas. |
| E2-07 Regresión y evidencia | E2-04, E2-05, E2-06 | `tests/probar_entrega2.py`, extensión del ejecutor, `evidencias/entrega2/ID_CORRIDA/` | Matriz de sección 13 y regresión E1 aprobadas sobre los mismos archivos identificados. |
| E2-08 Sustentación y revisión | E2-07 | `docs/entrega2/guia_sustentacion.md`, `resultado_validacion.md`, README | Ejecución reproducible, resultados numéricos y límites declarados; PR revisable. |

Orden de instalación previsto: preflight y permisos; estructura y carga de Entrega 1 en esquema nuevo; migración de soporte; especificación y cuerpo; triggers; verificación de objetos; fixtures y pruebas; refresco de MV y regresión de consultas. No se ejecutará la carga académica sobre una base ya poblada.

Antes de definir un índice adicional para la liquidación por checkout, revisar el plan de la consulta y los índices actuales. No añadir índices ni prometer mejoras de tiempo sin evidencia.

## 13. Matriz mínima de pruebas del incremento

**Todas las filas siguientes son pruebas planificadas, no resultados ejecutados.** Fixtures con importes calculados manualmente, separadas de la carga de 25.000 reservas. Los casos concurrentes usarán dos conexiones, sincronización explícita y tiempos de espera limitados.

| ID | Escenario | Resultado esperado |
|---|---|---|
| F01 | Tres noches en una temporada a 100 | Importe 300. |
| F02 | 29/06–03/07; junio 100 y julio 150 | Importe 500, dos tramos de dos noches. |
| F03 | 30/06–01/07 | Solo una noche de junio, importe 100. |
| F04 | 01/01/2024–02/01/2025 a 10 | 367 noches e importe 3.670. |
| F05 | Fechas nulas, con hora, iguales, invertidas y extremo máximo | Código de entrada/intervalo propio; cero escrituras. |
| F06 | Hueco, superposición, tarifa ausente, temporada con hora y hueco/solape que compensan noches | Cada anomalía identificada; nunca importe cero o temporada arbitraria. |
| F07 | Cambiar junio a 120 después de contratar el caso F02 | Nueva cotización 540; total y tramos del contrato conservan 500. |
| F08 | Tarifa y duración cuyo producto excede NUMBER(12,2) | Error monetario propio antes de intentar guardar un contrato fuera de capacidad. |
| R01 | Dos habitaciones, hospedaje 400 + 600 y servicios 60 + 40 | Cabecera 1.100; detalles, servicios y tramos conciliados. |
| R02 | Capacidad exacta, excedida y personas/cantidades fraccionarias | Capacidad exacta aceptada; los demás casos rechazados sin residuos. |
| R03 | IDs inexistentes/duplicados, otra sede, habitación en mantenimiento/fuera de servicio y fecha inválida con habitación ya ocupada | Error específico; ninguna reserva parcial. La fecha inválida se diagnostica antes del solape. |
| R04 | Fallo después de crear cabecera/detalles, con trabajo previo del llamador | Solo se revierte la llamada; el trabajo anterior permanece sin confirmarse. |
| R05 | Creación válida y posterior ROLLBACK del cliente | Desaparece toda la reserva; sin COMMIT oculto. |
| C01 | Dos sesiones, habitación inicialmente libre, misma estadía; primera hace COMMIT | Como máximo una reserva confirmable; la segunda rechaza solape tras obtener el lock. |
| C02 | Mismo caso, primera hace ROLLBACK | La segunda puede continuar cuando adquiere el lock. |
| C03 | Bloqueo retenido más que el límite configurado | Error temporal propio; sin filas parciales. |
| C04 | Habitaciones distintas y solicitudes de varias habitaciones en orden inverso | Progreso independiente; adquisición ordenada, sin deadlock originado por invertir la lista de entrada. |
| C05 | Cambio concurrente de tarifa durante captura | Importe y tramos de cada habitación proceden de la misma captura. |
| C06 | Una sesión inserta un detalle mientras otra cambia fechas de esa cabecera | El lock común de cabecera serializa la lectura; no queda un solape al confirmar ambas sesiones. |
| T01 | Contiguas, cruce parcial, intervalo contenido y contenedor | Contiguas aceptadas; tres formas de cruce rechazadas. |
| T02 | INSERT/UPDATE de varias filas que generan conflicto entre sí | Se rechaza la sentencia completa, sin `ORA-04091`. |
| T03 | Cambiar fechas o reactivar una CANCELADA que ahora cruza otra reserva | Rechazo del cambio; cabecera anterior conservada. |
| T04 | CANCELADA comparte noches; otra PENDIENTE las solicita | Cancelada no bloquea; pendiente sí bloquea una tercera solicitud. |
| A01 | Un usuario de prueba autorizado actualiza una tarifa | SESSION_USER identifica al actor que ejecutó el UPDATE; fecha UTC, sentencia e importes anterior/nuevo exactos. |
| A02 | Una sentencia cambia 100 tarifas | 100 eventos, un identificador común, sin pérdidas o duplicados. |
| A03 | UPDATE sin cambio de precio y sentencia que afecta cero filas | Cero eventos nuevos. |
| A04 | UPDATE seguido de ROLLBACK | Precios y auditoría vuelven al estado anterior. |
| A05 | UPDATE masivo que falla por precio inválido | Se revierte toda la sentencia y no queda auditoría parcial. |
| L01 | Finalizada 31/01–01/02, H=200, S=50, porcentaje de prueba 12 | Enero excluye; febrero base 250, comisión 30, neto 220. |
| L02 | Misma fecha en PENDIENTE, CONFIRMADA, CHECKED_IN y CANCELADA | Todas excluidas de liquidación. |
| L03 | Dos detalles H=100+200 y dos servicios S=10+20; comisión 12 | Base 330, comisión 39,60 y neto 290,40; sin producto cartesiano. |
| L04 | Repetir corte idéntico; variar importes fuente/tasa; retirar la última reserva elegible; corte DISPERSADA/PAGADA | Idéntico conserva ID/fecha/estado; diferencias monetarias o de política, incluida fuente ahora vacía, se rechazan sin sobrescribir. |
| L05 | Dos sesiones liquidan el mismo alojamiento/período | Un corte, resultado serializado y sin duplicados. |
| L06 | Fallo después de procesar el primer alojamiento del lote | Ninguna liquidación parcial del lote; trabajo previo del llamador preservado. |
| L07 | Mes sin actividad; porcentaje nulo/fuera de rango; período extremo | Sin actividad: cero filas nuevas. Parámetros inválidos: rechazo propio. |
| L08 | Corte legado sin porcentaje/criterio y cambio de TARIFA después de reservar | Legado no se certifica artificialmente; catálogo actual no cambia importes a liquidar. |
| I01 | Compilación e instalación repetida compatible | Paquete/cuerpo/triggers VALID, cero errores de USER_ERRORS y triggers habilitados. |
| I02 | Usuario de ejecución intenta DML directo y luego crea una reserva o liquida mediante el paquete | DML denegado y operaciones autorizadas por paquete. El actor de auditoría se comprueba por separado en A01. |
| I03 | Regresión de ocho consultas y 23 casos E1, más cancelación reutilizada | Contratos analíticos e históricos preservados; verificador operativo acepta la nueva regla acordada. |
| I04 | Comparar esquemas originales antes/después | `TURISMOUQ` y `TURISMOUQ_E1` sin alteraciones por la implementación aislada. |

## 14. Evidencia, cierre y condiciones para detenerse

La evidencia de Entrega 2 deberá incluir revisión Git y hashes de archivos ejecutados, versión de Oracle/clientes, esquema y configuración, errores esperados y observados, valores numéricos, estado de objetos y logs de ambas sesiones de concurrencia. Los resultados nuevos se guardarán separados de la evidencia histórica E1.

La demostración mínima mostrará: cotización 500; error propio de checkout; error de capacidad; rechazo de solape; reserva contigua válida; UPDATE masivo con auditoría; liquidación 250/30/220 con cursor parametrizado; ROLLBACK sin residuos; y consulta del paquete/triggers válidos. Después se ejecutará la regresión E1 y su refresco explícito de ocupación.

Se detendrá la implementación afectada si no está resuelto el encaje de los triggers con la rúbrica, aparece un contrato de datos incompatible, falta privilegio imprescindible, una prueba concurrente permite dos reservas cruzadas o una falla deja datos parciales. Se corregirá la causa; no se deshabilitarán restricciones o triggers para presentar una sustentación exitosa.

El incremento estará terminado cuando la matriz tenga evidencia real aprobada, las migraciones preserven los datos, la instalación pueda repetirse en otro esquema y documentación y PR describan exactamente lo implementado. **Este documento es planificación; sus propuestas y pruebas todavía no son una implementación realizada.**
