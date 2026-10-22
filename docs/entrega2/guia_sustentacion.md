# Guía de sustentación de Entrega 2

Esta guía demuestra el paquete y los controles de Entrega 2 sobre la carga académica de un esquema aislado. Las reservas originales de `TURISMOUQ` y la entrega corregida `TURISMOUQ_E1` se conservan. No ejecutar la carga otra vez sobre esas cuentas.

La corrida final `2026-10-22_124147` aprobó **40 de 40 casos E2, 23 regresiones E1, ocho consultas y esta demostración**. El [resultado de validación](resultado_validacion.md) enlaza los valores observados, los manifiestos del código ejecutado y cuatro controles adicionales de migración con legado.

## 1. Preparar la conexión desde CMD

Abrir CMD en la raíz del repositorio. En este equipo:

~~~bat
cd /d C:\Users\ASUS\Desktop\U_SEM7-8\BD_2\tourism\turismoUq
sqlplus / as sysdba
~~~

En SQL*Plus, seleccionar la PDB antes de administrar la cuenta aislada:

~~~sql
ALTER SESSION SET CONTAINER = XEPDB1;
SHOW CON_NAME
~~~

Si hace falta asignar una contraseña que conozca quien sustenta, usar el comando de SQL*Plus que la pide sin escribirla en el script:

~~~sql
PASSWORD TURISMOUQ_E2
~~~

Introducir y confirmar la contraseña en sus prompts. Este paso cambia únicamente la contraseña de esa cuenta de demostración; no reinstala el proyecto ni modifica las cuentas originales. Si el ejecutor creó otro prefijo, utilizar el nombre exacto de su propietario principal indicado en el manifiesto; no usar el usuario de fixtures terminado en `_TEST`.

Conectarse después como propietario, introduciendo la contraseña cuando SQL*Plus la solicite:

~~~sql
CONNECT TURISMOUQ_E2@//localhost:1521/XEPDB1
SHOW USER
ALTER SESSION SET ISOLATION_LEVEL = READ COMMITTED;
ALTER SESSION SET NLS_CALENDAR = 'GREGORIAN';
~~~

El puerto, servicio y nombre del esquema deben coincidir con el entorno instalado. No guardar contraseñas en comandos, archivos de evidencia ni capturas. Utilizar una conexión nueva, sin transacciones personales pendientes.

## 2. Ejecutar la demostración

Desde esa conexión y con CMD situado en la raíz del repositorio:

~~~sql
@05_demostracion_plsql.sql
~~~

[El script](../../05_demostracion_plsql.sql) verifica que la conexión sea la del propietario actual, rechaza SYS, SYSTEM, TURISMOUQ y TURISMOUQ_E1, y comprueba las 22 tablas, el paquete válido y los tres triggers habilitados. Admite nombres de esquema alternos para las corridas aisladas. No contiene DDL ni COMMIT; delimita su trabajo con un savepoint y revierte los cambios al terminar, también si encuentra un error.

Se necesita la carga académica con temporadas hasta el **15 de enero de 2027 incluido**, una habitación disponible y un alojamiento/mes de 2025 con reservas finalizadas y sin corte previo. La demostración selecciona esos identificadores de los datos; no presupone un cliente o habitación con ID específico. Si las precondiciones no existen, se detiene con un diagnóstico.

El rollback elimina las filas generadas y restaura el precio probado. Los generadores IDENTITY pueden consumir números aunque la transacción se revierta; los huecos de identidad no significan que haya quedado una reserva o auditoría confirmada.

## 3. Qué mostrar y cómo interpretarlo

1. **Propietario y objetos.** Mostrar el usuario real, el esquema y los estados VALID. Un objeto compilado por sí solo no demuestra sus reglas; las operaciones siguientes comprueban comportamiento.
2. **Función desde SQL.** Cotizar una habitación libre entre 14/01/2027 y 16/01/2027: son las noches del 14 y del 15; el checkout del 16 queda excluido. El importe mostrado procede de las tarifas del conjunto cargado. Los ejemplos controlados de 500 y 540 pertenecen a los fixtures de la suite, no a una tarifa inventada para esa habitación.
3. **Errores propios.** Mostrar `-20301` por checkout igual al check-in y `-20305` por capacidad excedida. El script verifica sus códigos; un error inesperado aborta la demostración.
4. **Reserva completa.** Crear una reserva PENDIENTE para esa habitación y comprobar que coincide con la cotización. La creación persiste el precio aplicado por tramos y el total dentro de la misma transacción.
5. **Solapamiento.** Repetir la solicitud para las mismas noches: debe producir `-20304`. La reserva PENDIENTE ya bloquea; CANCELADA es el estado que libera.
6. **Auditoría.** Subir en una unidad el precio de una tarifa, mostrar actor, fecha UTC, precio anterior/nuevo e identificador común de sentencia. El script exige un evento y hace un rollback local que restaura tanto precio como evento. Los contratos históricos no se revalúan.
7. **Liquidación y repetición.** Seleccionar un alojamiento/mes de 2025 con reservas FINALIZADA por checkout. El porcentaje **12** es un dato de demostración pasado obligatoriamente al procedimiento, no una comisión predeterminada del negocio. Se muestran hospedaje, servicios, base, comisión y neto. La segunda llamada debe crear cero cortes y conservar el mismo registro.
8. **Rollback final.** Mostrar el mensaje de cierre y los conteos restaurados. No ejecutar COMMIT para conservar la demostración: su propósito es dejar las filas como estaban.

Para interpretar la liquidación: base = hospedaje + servicios; comisión = ROUND(base × porcentaje / 100, 2); neto = base − comisión. El caso controlado H=200, S=50 y porcentaje 12 da 250/30/220. La carga académica puede producir importes distintos y el script muestra los realmente calculados.

## 4. Alcance de la evidencia

La demostración usa una conexión y cambios de una tarifa. Los casos de dos sesiones, cambio de 100 tarifas con un identificador común, rollback parcial, captura histórica, períodos y extremos de precisión pertenecen a la suite automatizada. Conservar sus logs y manifiesto junto al resultado; no atribuir esas pruebas concurrentes a esta ejecución manual.

La liquidación E2 considera solo FINALIZADA y mes del checkout. Las consultas analíticas E1 mantienen reservas no canceladas y mes del check-in. No presentar sus totales como si fueran la misma métrica.

El paquete no confirma transacciones por el usuario ni cobra pagos, dispersa dinero, instala jobs o modifica reservas mediante una API de edición. Los cambios administrativos de fechas y estado se ejercitan en pruebas para comprobar los controles.

## 5. Si una comprobación falla

Conservar el primer error y el contexto de la cuenta usada. Un rechazo de propietario o de objetos significa que falta preparar el esquema correcto; no resolverlo ejecutando la demostración como SYS ni deshabilitando triggers.

Si el script terminó con error, volver a conectarse al propietario, configurar READ COMMITTED y GREGORIAN y corregir la precondición indicada antes de repetir. No recargar datos sobre tablas pobladas ni sobrescribir un corte existente para hacer que la demostración pase.

La evidencia definitiva debe corresponder al código identificado en el manifiesto de [resultado_validacion.md](resultado_validacion.md).
