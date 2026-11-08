# Abrir TurismoUQ desde Windows

Este procedimiento es para el equipo que ya tiene Oracle XE y el esquema `TURISMOUQ_E3` preparados. Si aún no elegiste una clave, sigue [el paso de contraseña de Entrega 3](docs/entrega3/guia_sustentacion.md#usar-la-gui-en-windows). El navegador muestra la interfaz; Oracle conserva los datos. Se necesitan ambos procesos encendidos.

## Cada vez que quieras usarla

1. Abre el Explorador de archivos y entra en:

   ```text
   C:\Users\ASUS\Desktop\U_SEM7-8\BD_2\tourism\turismoUq
   ```

2. Haz doble clic en **`run_app.cmd`**. Puede aparecer como `run_app` con tipo «Script de comandos de Windows» si tienes ocultas las extensiones. `run_app.sh` corresponde a Linux.
3. Espera a que aparezca `Abriendo TurismoUQ` y se abra el navegador. Si ya estaba iniciada, aparecerá `TurismoUQ ya esta encendido` y se abrirá la instancia existente. Mantén abierta la ventana original de comandos: allí se está ejecutando la aplicación.
4. Si el navegador no se abre automáticamente, visita **<http://127.0.0.1:8501/>** desde Chrome, Edge u otro navegador de este mismo computador.
5. En la barra lateral de la interfaz, completa:

   | Campo | Valor |
   | --- | --- |
   | Host / IP | `localhost` |
   | Puerto | `1521` |
   | Servicio / PDB | `xepdb1` |
   | Cuenta Oracle | Elige **Otro** para usar un rol, o `TURISMOUQ_E3` para el propietario |
   | Usuario personalizado / esquema propietario | `TURISMOUQ_E3_USR_RECEP` / `TURISMOUQ_E3` para recepción |
   | Contraseña | La contraseña que elegiste para esta cuenta de Oracle |

6. Pulsa **Probar Conexión**. Cuando aparezca «Conectado», selecciona el módulo que quieras usar. Si cambias un dato de conexión, debes validarla de nuevo.
7. En **Reserva y pago · Entrega 3**, puedes simular una operación antes de registrar un pago recibido. La barra lateral muestra los módulos que tu cuenta puede usar.

La conexión de GrownupsVet y el usuario `grownupsvet_app` corresponden a otra base. Usa la contraseña de la cuenta de TurismoUQ que elegiste. La cuenta `TURISMOUQ_E2` sigue disponible para los módulos históricos.

## Apagar y volver a abrir

Para apagar la interfaz, vuelve a su ventana de comandos y presiona **Ctrl+C**. Si Windows pregunta si deseas terminar el trabajo por lotes, responde la opción afirmativa que muestre: **S** o **Y**, según el idioma. Cerrar solamente la pestaña del navegador deja el servidor encendido.

Para volver a abrirla, repite el doble clic en `run_app.cmd`. Después de reiniciar o apagar el computador también debes ejecutar este archivo; guardar el enlace del navegador no enciende el servidor.

Si TurismoUQ ya está ejecutándose en el puerto 8501, el lanzador comprueba que pertenece a este proyecto y abre su enlace sin iniciar una segunda instancia.

## Primera ejecución del lanzador

El lanzador usa `.venv\Scripts\python.exe`. Si falta el entorno, lo crea con el Python instalado; si faltan dependencias, instala `app/requirements.txt`. En esa preparación se necesita acceso a internet. Las siguientes aperturas reutilizan el entorno.

El lanzador también comprueba los servicios de Oracle. Si indica que alguno está detenido:

1. Presiona **Windows+R**, escribe `services.msc` y pulsa Enter.
2. Busca **OracleServiceXE** y **OracleOraDB21Home1TNSListener**.
3. En el servicio detenido, usa clic derecho → **Iniciar**. Windows puede pedir permisos de administrador para esta operación.
4. Cuando ambos estén «En ejecución», vuelve a abrir `run_app.cmd`.

El lanzador no cambia la configuración de los servicios. Abrir la interfaz no requiere ejecutar el DDL, la carga de datos, los validadores ni SQL*Plus.

## Alternativa desde PowerShell

Abre PowerShell y ejecuta estas dos líneas:

```powershell
cd "C:\Users\ASUS\Desktop\U_SEM7-8\BD_2\tourism\turismoUq"
.\run_app.cmd
```

Para revisar los requisitos sin iniciar la interfaz ni instalar dependencias:

```powershell
.\run_app.cmd -CheckOnly
```

Para iniciar el servidor y abrir tú mismo el enlace, sin apertura automática del navegador:

```powershell
.\run_app.cmd -NoBrowser
```

No necesitas activar el entorno virtual ni modificar permanentemente la política de PowerShell. El archivo `.cmd` invoca el script del proyecto con una configuración limitada a ese proceso.

## Si algo falla

| Mensaje o situación | Qué hacer |
| --- | --- |
| El navegador no puede conectarse a `127.0.0.1:8501` | Abre `run_app.cmd`, espera a que aparezca la dirección y mantén su ventana abierta. Si aparece un error, léelo antes de cerrar la ventana. |
| Servicio de Oracle detenido | Sigue los pasos de `services.msc` indicados arriba y vuelve a abrir el lanzador. |
| No se encuentra Python | Instala Python 3 con su lanzador `py`. El entorno verificado en este equipo utiliza Python 3.14. |
| Falló la instalación de dependencias | Comprueba internet y ejecuta `run_app.cmd` otra vez. El mensaje de `pip` muestra qué instalación falló. |
| Puerto 8501 ocupado por otro proceso | Revisa si tienes otra aplicación abierta en ese puerto y detén esa aplicación desde su propia consola con Ctrl+C. El mensaje muestra el PID; el lanzador no termina procesos ajenos. |
| `ORA-01017` | Verifica el usuario Oracle, servicio `xepdb1` y su contraseña. Corrige los campos antes de volver a pulsar Probar Conexión. |
| `ORA-28000` | La cuenta está bloqueada. No sigas probando claves; revisa el desbloqueo administrativo de esa cuenta. La [guía de Entrega 3](docs/entrega3/guia_sustentacion.md) explica cómo elegir una contraseña local si la olvidaste. |
| El PIVOT parece casi vacío | Revisa el año del selector. Con la carga preparada, 2025 permite ver un año completo. |
