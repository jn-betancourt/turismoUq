# Modelado de Entidades - TurismoUQ

Documento de análisis conceptual y definición de propiedades para la plataforma de reservas turísticas del Quindío (**TurismoUQ**), basado en el contexto del proyecto (código 12338, motor **Oracle XE 21c**), el nuevo diagrama conceptual actualizado ([diagrama-e.drawio.html](file:///home/juan/obsidian/notes/bases%202/diagrama-e.drawio.html)) y las extensiones derivadas del análisis de normalización de dominio para la Entrega 1.

## 1. Evidencia del Modelo Conceptual y Jerarquía de Usuarios

En la versión actualizada del modelo conceptual se incorporan los siguientes fundamentos de diseño:
1. **Jerarquía de Especialización / Generalización ("Es un"):**
   - La entidad general **`USUARIO_SISTEMA`** se especializa mediante una relación de herencia (*"Es un"*) hacia:
     - **`CLIENTE`**: Usuario del sistema que crea reservas, realiza pagos y emite reseñas.
     - **`PROPIETARIO`**: Usuario del sistema que crea y administra establecimientos turísticos (`ALOJAMIENTO`).
     - Perfiles operativos del sistema (`RECEPCION`, `ADMIN_ALOJAMIENTO`, `GERENTE`, `AUDITOR`).
2. **Reconfiguración de Vínculos del Dominio:**
   - **`PROPIETARIO`** (1) —— `Crea` —— (1..n) **`ALOJAMIENTO`**.
   - **`RESERVA`** (1) —— `Tiene` —— (0..n) **`RESENA`**, la cual a su vez (0..n) —— `Referencia` —— (1) **`ALOJAMIENTO`**.
   - Tablas de referencias cruzadas: **`RESERVA_HABITACION`** (multi-habitación) y **`RESERVA_SERVICIO`** (consumos de actividades).
3. **Tablas Extensivas de Normalización (Entrega 1):**
   - Normalización de comodidades (`COMODIDAD`, `ALOJAMIENTO_COMODIDAD`), tipologías de cuarto (`TIPO_HABITACION`), soporte de auditoría (`AUDITORIA_TARIFA`), persistencia de liquidaciones (`LIQUIDACION_MENSUAL`) y almacenamiento en tablespace propio (`HISTORICO_RESERVA`).

## 2. Definición de Entidades y Propiedades (Modelo Completo)

A continuación se definen las 21 entidades del modelo físico para la Entrega 1, detallando sus atributos, restricciones y el análisis de normalización aplicado:

### 1. USUARIO_SISTEMA (Superentidad de Identidad y Seguridad)
- **Razón:** Proveer la base de autenticación centralizada, credenciales seguras y control de acceso unificado para todas las personas que interactúan con la plataforma.
- **Rol:** Actuar como supertipo en la jerarquía *"Es un"*, gobernando la seguridad, credenciales de acceso y segregación de perfiles (recepción, administrador de alojamiento, gerente, auditor, cliente y propietario).
- **Propiedades:**
  - `id_usuario` (NUMBER, PK): Identificador único de la cuenta de usuario.
  - `username` (VARCHAR2, NOT NULL, UNIQUE): Nombre de usuario para inicio de sesión.
  - `password_hash` (VARCHAR2, NOT NULL): Contraseña almacenada mediante hash criptográfico seguro.
  - `nombre_completo` (VARCHAR2, NOT NULL): Nombres y apellidos del titular de la cuenta.
  - `email` (VARCHAR2, NOT NULL, UNIQUE): Correo electrónico principal para notificaciones.
  - `tipo_usuario` (VARCHAR2, NOT NULL, CHECK in ('CLIENTE', 'PROPIETARIO', 'RECEPCION', 'ADMIN_ALOJAMIENTO', 'GERENTE', 'AUDITOR')): Discriminador de rol/subtipo para la especialización *"Es un"*.
  - `estado` (VARCHAR2, NOT NULL, CHECK in ('ACTIVO', 'INACTIVO', 'BLOQUEADO')): Estado operacional de la cuenta.
  - `fecha_registro` (TIMESTAMP, NOT NULL, DEFAULT SYSTIMESTAMP): Momento de creación del usuario.
- **Análisis de normalización:**
  - *Herencia y ausencia de nulos:* Centraliza las credenciales comunes evitando dispersar tablas de login independientes. Los atributos exclusivos de negocio de turistas o propietarios se trasladan a sus respectivas subtablas 1:1.
  - *Extensiones señaladas:* Perfiles dinámicos desprendibles a `ROL_PERMISO` y monitoreo a `HISTORIAL_SESION`.

---

### 2. PROPIETARIO (Subentidad / Especialización de Usuario)
- **Razón:** Modelar a los titulares comerciales y personas responsables de los 60 alojamientos turísticos en el departamento del Quindío.
- **Rol:** Especializar a `USUARIO_SISTEMA` para vincular legal y administrativamente la propiedad de uno o más alojamientos, ser el receptor de las liquidaciones mensuales de ingresos y coordinar la operación.
- **Propiedades:**
  - `id_usuario` (NUMBER, PK, FK -> `USUARIO_SISTEMA.id_usuario`): Identificador del usuario que hereda los atributos base de la cuenta.
  - `documento_identidad` (VARCHAR2, NOT NULL, UNIQUE): Cédula de ciudadanía o NIT del propietario o representante legal.
  - `telefono_contacto` (VARCHAR2, NOT NULL): Línea telefónica directa de contacto y notificaciones comerciales.
  - `numero_cuenta_bancaria` (VARCHAR2, NULL): Cuenta bancaria donde la plataforma abona la liquidación mensual de ingresos del alojamiento.
- **Análisis de normalización:**
  - *Especialización 1:1:* Evita columnas huérfanas en la superentidad.
  - *Desprendimiento bancario:* Siguiendo formas avanzadas de normalización, si un propietario maneja múltiples cuentas o entidades financieras, la información bancaria se desprende a `CUENTA_BANCARIA_PROPIETARIO`.

---

### 3. CLIENTE (Subentidad / Especialización de Usuario)
- **Razón:** Registrar a los turistas nacionales y extranjeros (3.000 clientes) que contratan hospedajes y servicios en la región.
- **Rol:** Especializar a `USUARIO_SISTEMA` como titular de las reservas formalizadas, emisor directo de los pagos y responsable de publicar reseñas de satisfacción.
- **Propiedades:**
  - `id_usuario` (NUMBER, PK, FK -> `USUARIO_SISTEMA.id_usuario`): Identificador del usuario heredado de la superentidad.
  - `tipo_documento` (VARCHAR2, NOT NULL, CHECK in ('CC', 'CE', 'PASAPORTE', 'TI', 'NIT')): Tipo de documento legal.
  - `numero_documento` (VARCHAR2, NOT NULL, UNIQUE): Número de documento de identificación.
  - `telefono` (VARCHAR2, NOT NULL): Número telefónico móvil para contacto y envío de confirmaciones.
  - `ciudad_origen` (VARCHAR2, NULL): Ciudad o país de procedencia (requerido para análisis de demanda turística regional).
- **Análisis de normalización:**
  - *Desprendimiento geográfico:* De aquí se desprende la normalización de procedencia hacia un catálogo formal `PAIS` / `DEPARTAMENTO` para evitar inconsistencias tipográficas en el análisis demográfico.
  - *Acompañantes:* Desprendible a `HUESPED_RESERVA`.

---

### 4. MUNICIPIO
- **Razón:** Representar la división territorial y geográfica del Quindío donde se concentra la oferta turística (12 municipios).
- **Rol:** Servir como eje espacial para la agrupación de alojamientos y posibilitar los análisis estadísticos exigidos (ocupación mensual con PIVOT, e ingresos con ROLLUP/CUBE por municipio).
- **Propiedades:**
  - `id_municipio` (NUMBER, PK): Identificador único del municipio.
  - `nombre` (VARCHAR2, NOT NULL, UNIQUE): Denominación oficial del municipio (Armenia, Salento, Filandia, Montenegro, Quimbaya, Calarcá, Circasia, La Tebaida, Pijao, Génova, Buenavista, Córdoba).
- **Análisis de normalización:**
  - Cumple 3FN estricta para agregaciones territoriales directas. Desprende atractivos hacia `SITIO_INTERES` y fotos hacia `FOTO_MUNICIPIO`.

---

### 5. TIPO_ALOJAMIENTO
- **Razón:** Categorizar la heterogénea oferta de hospedaje presente en el departamento.
- **Rol:** Permitir la clasificación de los establecimientos para consultas agregadas (ingresos por tipo de alojamiento con CUBE/ROLLUP) y filtrado de búsquedas.
- **Propiedades:**
  - `id_tipo_alojamiento` (NUMBER, PK): Identificador del tipo de hospedaje.
  - `nombre` (VARCHAR2, NOT NULL, UNIQUE): Modalidad ('Finca cafetera', 'Hotel', 'Glamping', 'Hostal').
- **Análisis de normalización:**
  - Catálogo cerrado en 3FN que elimina redundancia de cadenas de texto en los 60 alojamientos.

---

### 6. ALOJAMIENTO
- **Razón:** Representar cada uno de los 60 establecimientos comerciales prestadores de servicio de hospedaje en el Quindío.
- **Rol:** Centralizar la oferta del prestador, agrupar las habitaciones e inventario de servicios, vincularse al propietario responsable y constituir el objeto del proceso masivo de liquidación mensual.
- **Propiedades:**
  - `id_alojamiento` (NUMBER, PK): Identificador único del establecimiento.
  - `id_propietario` (NUMBER, FK -> `PROPIETARIO.id_usuario`, NOT NULL): Propietario que crea y administra el establecimiento (relación `Crea`).
  - `id_municipio` (NUMBER, FK -> `MUNICIPIO.id_municipio`, NOT NULL): Municipio del Quindío donde está ubicado físicamente.
  - `id_tipo_alojamiento` (NUMBER, FK -> `TIPO_ALOJAMIENTO.id_tipo_alojamiento`, NOT NULL): Categoría de hospedaje.
  - `nombre` (VARCHAR2, NOT NULL): Nombre comercial del alojamiento.
  - `direccion` (VARCHAR2, NOT NULL): Vereda, carretera o dirección urbana.
  - `telefono` (VARCHAR2, NOT NULL): Teléfono de recepción o atención.
  - `estado` (VARCHAR2, NOT NULL, CHECK in ('ACTIVO', 'INACTIVO', 'MANTENIMIENTO')): Estado de operación en la plataforma.
- **Análisis de normalización:**
  - *Eliminación de atributos multivaluados (1FN):* Las comodidades (piscina, wifi, etc.) no se almacenan como columnas booleanas sueltas, sino que se normalizan a la relación N:M mediante `COMODIDAD` y `ALOJAMIENTO_COMODIDAD`.

---

### 7. HABITACION
- **Razón:** Modelar las 400 unidades físicas de alojamiento distribuidas en los 60 establecimientos.
- **Rol:** Representar el espacio físico individual reservable, controlar la asignación sin solapamientos y asociarse a las tarifas por temporada.
- **Propiedades:**
  - `id_habitacion` (NUMBER, PK): Identificador único de la habitación.
  - `id_alojamiento` (NUMBER, FK -> `ALOJAMIENTO.id_alojamiento`, NOT NULL): Establecimiento al que pertenece.
  - `id_tipo_habitacion` (NUMBER, FK -> `TIPO_HABITACION.id_tipo_habitacion`, NOT NULL): Categoría tipológica y de capacidad.
  - `numero_habitacion` (VARCHAR2, NOT NULL): Identificador o nomenclatura interna (ej. '101', 'Cabaña El Cafeto').
  - `estado` (VARCHAR2, NOT NULL, CHECK in ('DISPONIBLE', 'MANTENIMIENTO', 'FUERA_SERVICIO')): Estado físico para asignación.
- **Análisis de normalización:**
  - *Normalización a 3FN:* La capacidad y descripción de confort se desacoplan hacia `TIPO_HABITACION`, evitando duplicar datos idénticos en las 400 habitaciones.
  - *Restricción compuesta:* `UNIQUE (id_alojamiento, numero_habitacion)` para asegurar unicidad dentro de cada establecimiento.

---

### 8. TEMPORADA
- **Razón:** Capturar la marcada estacionalidad de la demanda turística del Quindío (Semana Santa, mitad de año, puentes festivos, diciembre–enero y temporada baja).
- **Rol:** Definir las ventanas de fechas en el calendario que gobiernan la aplicación de precios dinámicos para el cálculo de estadías con cruce de temporadas.
- **Propiedades:**
  - `id_temporada` (NUMBER, PK): Identificador único de la temporada.
  - `nombre` (VARCHAR2, NOT NULL): Nombre del periodo ('Semana Santa', 'Mitad de año', 'Puentes festivos', 'Diciembre-Enero', 'Baja').
  - `fecha_inicio` (DATE, NOT NULL): Fecha inicial de vigencia.
  - `fecha_fin` (DATE, NOT NULL, CHECK fecha_fin >= fecha_inicio): Fecha final de vigencia.
  - `tipo_temporada` (VARCHAR2, NOT NULL, CHECK in ('ALTA', 'MEDIA', 'BAJA')): Grado de demanda estacional.
- **Análisis de normalización:**
  - Normaliza la estacionalidad del negocio turístico como una dimensión temporal independiente, permitiendo consultas analíticas de ingresos agrupadas con `ROLLUP` y `CUBE`.

---

### 9. TARIFA
- **Razón:** Establecer el precio de hospedaje de cada habitación en función de la temporada vigente.
- **Rol:** Proveer el insumo de cálculo para la función `fn_valor_estadia` y ser objeto del disparador de auditoría a nivel de sentencia (quién, cuándo, valor anterior y nuevo).
- **Propiedades:**
  - `id_tarifa` (NUMBER, PK): Identificador del registro tarifario.
  - `id_habitacion` (NUMBER, FK -> `HABITACION.id_habitacion`, NOT NULL): Habitación asociada.
  - `id_temporada` (NUMBER, FK -> `TEMPORADA.id_temporada`, NOT NULL): Temporada en la que rige.
  - `precio_noche` (NUMBER(12,2), NOT NULL, CHECK > 0): Valor monetario por noche en moneda local.
- **Análisis de normalización:**
  - *Restricción compuesta:* `UNIQUE (id_habitacion, id_temporada)` que garantiza unicidad de precio por par habitación-temporada.
  - *Segregación histórica:* No sobreescribe cambios sin registro; se conecta con `AUDITORIA_TARIFA`.

---

### 10. RESERVA
- **Razón:** Formalizar la transacción principal del negocio correspondiente a la contratación de alojamiento por parte de un cliente (25.000 reservas en 2024–2026).
- **Rol:** Centralizar el ciclo de vida de la estadía, controlando las fechas de check-in, check-out (validando checkout > checkin), estado de la reserva y consolidado económico.
- **Propiedades:**
  - `id_reserva` (NUMBER, PK): Identificador único de la reserva.
  - `id_cliente` (NUMBER, FK -> `CLIENTE.id_usuario`, NOT NULL): Cliente que crea la reserva (relación `Crea`).
  - `id_alojamiento` (NUMBER, FK -> `ALOJAMIENTO.id_alojamiento`, NULLABLE): Alojamiento donde se realiza la estancia (relación `Tiene`).
  - `fecha_reserva` (TIMESTAMP, NOT NULL, DEFAULT SYSTIMESTAMP): Momento exacto de registro en el motor.
  - `fecha_checkin` (DATE, NOT NULL): Fecha de ingreso.
  - `fecha_checkout` (DATE, NOT NULL, CHECK fecha_checkout > fecha_checkin): Fecha de salida pactada.
  - `estado` (VARCHAR2, NOT NULL, CHECK in ('PENDIENTE', 'CONFIRMADA', 'CHECKED_IN', 'FINALIZADA', 'CANCELADA')): Estado del contrato.
  - `valor_total` (NUMBER(12,2), NOT NULL, CHECK >= 0): Valor global liquidado (habitaciones + servicios complementarios).
- **Análisis de normalización:**
  - *Desacoplamiento de detalles M:N:* No incluye arreglos de habitaciones ni servicios en la cabecera; se delegan a `RESERVA_HABITACION` y `RESERVA_SERVICIO`.

---

### 11. RESERVA_HABITACION (Tabla de Referencia Cruzada N:M)
- **Razón:** Resolver la relación muchos a muchos entre reservas y habitaciones, respondiendo a la decisión de diseño de soportar que una reserva tome varias habitaciones simultáneas.
- **Rol:** Detallar individualmente cada habitación asignada a la reserva, registrar el número de huéspedes hospedados (para validar capacidad) y almacenar el valor liquidado por las temporadas atravesadas (`fn_valor_estadia`).
- **Propiedades:**
  - `id_reserva` (NUMBER, FK -> `RESERVA.id_reserva`, NOT NULL): Reserva a la que pertenece el renglón.
  - `id_habitacion` (NUMBER, FK -> `HABITACION.id_habitacion`, NOT NULL): Habitación reservada.
  - `personas_hospedadas` (NUMBER, NOT NULL, CHECK > 0): Conteo de huéspedes en esta habitación.
  - `precio_estadia_habitacion` (NUMBER(12,2), NOT NULL, CHECK >= 0): Monto liquidado para la habitación según las tarifas de cada temporada que atraviese la estadía.
- **Análisis de normalización:**
  - *Resolución N:M y clave compuesta:* `PRIMARY KEY (id_reserva, id_habitacion)`. Asegura que una reserva pueda tomar múltiples habitaciones sin redundar datos del cliente ni de fechas generales.

---

### 12. PAGO
- **Razón:** Documentar las operaciones monetarias realizadas para confirmar o amortizar una reserva, garantizando atomicidad transaccional.
- **Rol:** Respaldar el procedimiento atómico con SAVEPOINT y rollback parcial exigido en la Entrega 3, vinculando al cliente que realiza el desembolso con la reserva que genera la obligación.
- **Propiedades:**
  - `id_pago` (NUMBER, PK): Identificador único de la transacción.
  - `id_reserva` (NUMBER, FK -> `RESERVA.id_reserva`, NOT NULL): Reserva que genera la transacción (relación `Genera`).
  - `id_cliente` (NUMBER, FK -> `CLIENTE.id_usuario`, NOT NULL): Cliente que efectúa el pago (relación `Realiza`).
  - `fecha_pago` (TIMESTAMP, NOT NULL, DEFAULT SYSTIMESTAMP): Momento de procesamiento.
  - `monto` (NUMBER(12,2), NOT NULL, CHECK > 0): Cantidad monetaria pagada.
  - `metodo_pago` (VARCHAR2, NOT NULL, CHECK in ('TARJETA_CREDITO', 'TARJETA_DEBITO', 'TRANSFERENCIA', 'PSE', 'EFECTIVO')): Medio de pago utilizado.
  - `estado_pago` (VARCHAR2, NOT NULL, CHECK in ('APROBADO', 'PENDIENTE', 'RECHAZADO', 'REEMBOLSADO')): Estado de la transacción financiera.
- **Análisis de normalización:**
  - Permite que una reserva tenga 1 o múltiples pagos (anticipos, abonos o pagos totales) sin violar la 1FN.

---

### 13. SERVICIO
- **Razón:** Catalogar la oferta de productos y actividades turísticas complementarias al hospedaje (tours del café, pasadías, transporte, alimentación).
- **Rol:** Definir las opciones comerciales que cada establecimiento ofrece para enriquecer la experiencia y generar ingresos adicionales.
- **Propiedades:**
  - `id_servicio` (NUMBER, PK): Identificador único del servicio.
  - `id_alojamiento` (NUMBER, FK -> `ALOJAMIENTO.id_alojamiento`, NOT NULL): Establecimiento que lo presta.
  - `nombre` (VARCHAR2, NOT NULL): Nombre del servicio complementario.
  - `precio_unitario` (NUMBER(10,2), NOT NULL, CHECK >= 0): Precio estándar de contratación.
  - `estado` (VARCHAR2, NOT NULL, CHECK in ('ACTIVO', 'INACTIVO')): Disponibilidad del servicio en la plataforma.
- **Análisis de normalización:**
  - Entidad de catálogo desacoplada en 3FN que asocia cada actividad a su respectivo alojamiento.

---

### 14. RESERVA_SERVICIO (Tabla de Referencia Cruzada N:M)
- **Razón:** Detallar las 40.000 líneas de servicios complementarios contratadas por los clientes en sus reservas.
- **Rol:** Asociar los consumos específicos a una reserva, congelando la cantidad y la tarifa unitaria aplicada al momento de contratar.
- **Propiedades:**
  - `id_reserva` (NUMBER, FK -> `RESERVA.id_reserva`, NOT NULL): Reserva que contrata el servicio.
  - `id_servicio` (NUMBER, FK -> `SERVICIO.id_servicio`, NOT NULL): Servicio consumido.
  - `cantidad` (NUMBER, NOT NULL, CHECK > 0): Unidades o personas contratadas.
  - `precio_unitario_aplicado` (NUMBER(10,2), NOT NULL, CHECK >= 0): Valor unitario cobrado al momento de la contratación.
  - `subtotal` (NUMBER(12,2), NOT NULL, CHECK >= 0): Total resultante de la línea (`cantidad * precio_unitario_aplicado`).
- **Análisis de normalización:**
  - *Clave compuesta:* `PRIMARY KEY (id_reserva, id_servicio)`. Congela el precio histórico de contratación aislando el valor pactado de futuros aumentos en el catálogo de `SERVICIO`.

---

### 15. RESENA
- **Razón:** Recoger las opiniones y calificaciones cuantitativas emitidas por los turistas tras culminar su hospedaje.
- **Rol:** Medir la satisfacción del cliente y consolidar la reputación del alojamiento (relación `Tiene` desde Reserva y `Referencia` hacia Alojamiento).
- **Propiedades:**
  - `id_resena` (NUMBER, PK): Identificador único de la reseña.
  - `id_reserva` (NUMBER, FK -> `RESERVA.id_reserva`, NOT NULL): Reserva sobre la cual se emite la opinión (relación `Tiene`).
  - `id_alojamiento` (NUMBER, FK -> `ALOJAMIENTO.id_alojamiento`, NOT NULL): Establecimiento calificado (relación `Referencia`).
  - `calificacion` (NUMBER, NOT NULL, CHECK between 1 and 5): Puntuación de 1 a 5 estrellas.
  - `comentario` (VARCHAR2, NULL): Texto descriptivo con la experiencia del turista.
  - `fecha_resena` (TIMESTAMP, NOT NULL, DEFAULT SYSTIMESTAMP): Momento de emisión de la reseña.
- **Análisis de normalización:**
  - *Restricción de unicidad:* `UNIQUE (id_reserva)` garantiza que solo exista una reseña por estadía finalizada.

---

### 16. TIPO_HABITACION (Normalización de Capacidad y Categoría)
- **Razón:** Desacoplar la clasificación tipológica y la capacidad estándar de la habitación de su instancia física concreta.
- **Rol:** Estandarizar las categorías de habitaciones ('Sencilla', 'Doble estándar', 'Familiar', 'Suite', 'Cabaña premium') para evitar anomalías de modificación y redundancia en el aforo de las 400 habitaciones.
- **Propiedades:**
  - `id_tipo_habitacion` (NUMBER, PK): Identificador único de la categoría de habitación.
  - `nombre` (VARCHAR2, NOT NULL, UNIQUE): Nombre descriptivo de la categoría.
  - `capacidad_estandar` (NUMBER, NOT NULL, CHECK > 0): Número máximo de huéspedes permitido por estándar.
  - `descripcion` (VARCHAR2, NULL): Especificaciones generales de confort y distribución.
- **Análisis de normalización:**
  - *Cumplimiento estricto de 3FN:* Elimina la dependencia funcional transitiva en `HABITACION` donde `capacidad` dependía conceptualmente del tipo de habitación y se repetía idénticamente a lo largo de cientos de registros. Permite a `HABITACION` heredar de forma limpia su aforo base y facilita la validación de excepciones en `sp_crear_reserva`.

---

### 17. COMODIDAD (Catálogo de Instalaciones y Amenities)
- **Razón:** Catalogar las instalaciones, servicios de infraestructura y comodidades que ofrece la oferta turística del Quindío (piscina, wifi, jacuzzi, mirador cafetero, parqueadero, sendero ecológico, pet-friendly).
- **Rol:** Centralizar el maestro de comodidades para posibilitar búsquedas analíticas avanzadas, filtros por servicios y consultas cruzadas de valor agregado (Consulta 8).
- **Propiedades:**
  - `id_comodidad` (NUMBER, PK): Identificador único de la comodidad.
  - `nombre` (VARCHAR2, NOT NULL, UNIQUE): Nombre del servicio o instalación.
  - `categoria` (VARCHAR2, NOT NULL): Agrupador temático ('Recreación', 'Conectividad', 'Bienestar', 'Logística').
  - `icono` (VARCHAR2, NULL): Referencia visual o identificador gráfico.
- **Análisis de normalización:**
  - *Cumplimiento de 1FN:* Evita crear atributos multivaluados (listas de comodidades separadas por comas) o una proliferación de múltiples columnas booleanas (`tiene_piscina`, `tiene_wifi`, etc.) dentro de la tabla `ALOJAMIENTO`.

---

### 18. ALOJAMIENTO_COMODIDAD (Tabla Asociativa M:N)
- **Razón:** Resolver la relación muchos a muchos (M:N) entre los 60 establecimientos y el catálogo de comodidades.
- **Rol:** Vincular qué comodidades específicas posee cada alojamiento, permitiendo registrar si el servicio tiene costo adicional o está incluido en la tarifa.
- **Propiedades:**
  - `id_alojamiento` (NUMBER, FK -> `ALOJAMIENTO.id_alojamiento`, NOT NULL): Alojamiento que dispone de la instalación.
  - `id_comodidad` (NUMBER, FK -> `COMODIDAD.id_comodidad`, NOT NULL): Comodidad ofrecida.
  - `es_gratuito` (CHAR(1), NOT NULL, CHECK in ('S', 'N'), DEFAULT 'S'): Indica si está incluido en el hospedaje o requiere tarifa extra.
- **Análisis de normalización:**
  - *Cumplimiento de 2FN y 3FN en relaciones compuestas:* Resuelve la relación N:M mediante clave primaria compuesta `PRIMARY KEY (id_alojamiento, id_comodidad)`, garantizando que ningún atributo dependa parcialmente de la clave.

---

### 19. AUDITORIA_TARIFA (Persistencia de Auditoría DDL)
- **Razón:** Registrar la trazabilidad histórica inmutable de cualquier alteración en los precios por noche de las habitaciones.
- **Rol:** Servir de receptáculo físico en el DDL para el disparador a nivel de sentencia exigido en la Entrega 2, almacenando quién, cuándo y cuáles fueron los valores anterior y nuevo.
- **Propiedades:**
  - `id_auditoria` (NUMBER, PK): Identificador secuencial del evento de auditoría.
  - `id_tarifa` (NUMBER, FK -> `TARIFA.id_tarifa`, NOT NULL): Tarifa objeto del cambio.
  - `usuario_oracle` (VARCHAR2, NOT NULL): Usuario del motor de base de datos que ejecutó la sentencia (`USER` o `SYS_CONTEXT`).
  - `fecha_cambio` (TIMESTAMP, NOT NULL, DEFAULT SYSTIMESTAMP): Marca de tiempo precisa de la modificación.
  - `precio_anterior` (NUMBER(12,2), NOT NULL): Valor de la tarifa previo a la actualización.
  - `precio_nuevo` (NUMBER(12,2), NOT NULL): Nuevo valor asignado a la tarifa.
  - `operacion` (VARCHAR2, NOT NULL, CHECK in ('UPDATE', 'DELETE')): Tipo de operación DML interceptada.
- **Análisis de normalización:**
  - *Aislamiento temporal e histórico:* Evita sobreescribir destructivamente el estado pasado en `TARIFA`. Cumple con el principio de segregación temporal de datos operacionales vs datos de auditoría contable.

---

### 20. LIQUIDACION_MENSUAL (Persistencia de Cortes Contables)
- **Razón:** Almacenar los resultados financieros consolidados del proceso masivo de liquidación mensual por alojamiento.
- **Rol:** Persistir el corte de ingresos devengados por hospedaje y servicios complementarios, la comisión retenida por TurismoUQ y el valor neto a transferir al propietario, sirviendo de destino para el cursor explícito parametrizado de la Entrega 2.
- **Propiedades:**
  - `id_liquidacion` (NUMBER, PK): Identificador único del corte mensual.
  - `id_alojamiento` (NUMBER, FK -> `ALOJAMIENTO.id_alojamiento`, NOT NULL): Establecimiento liquidado.
  - `periodo_anio` (NUMBER(4), NOT NULL): Año contable del corte (ej. 2025).
  - `periodo_mes` (NUMBER(2), NOT NULL, CHECK between 1 and 12): Mes liquidado.
  - `total_hospedaje` (NUMBER(14,2), NOT NULL, CHECK >= 0): Sumatoria liquidada por habitaciones.
  - `total_servicios` (NUMBER(14,2), NOT NULL, CHECK >= 0): Sumatoria liquidada por servicios adicionales.
  - `comision_plataforma` (NUMBER(14,2), NOT NULL, CHECK >= 0): Monto o porcentaje retenido por la plataforma.
  - `neto_propietario` (NUMBER(14,2), NOT NULL, CHECK >= 0): Saldo a favor a desembolsar al propietario.
  - `fecha_liquidacion` (DATE, NOT NULL, DEFAULT SYSDATE): Fecha de procesamiento contable.
  - `estado` (VARCHAR2, NOT NULL, CHECK in ('CALCULADA', 'DISPERSADA', 'PAGADA')): Estado del pago de liquidación.
- **Análisis de normalización:**
  - *Restricción compuesta de periodicidad:* `UNIQUE (id_alojamiento, periodo_anio, periodo_mes)` para impedir dobles liquidaciones en el mismo periodo para el mismo establecimiento. Garantiza la atomicidad de los cierres contables mensuales.

---

### 21. HISTORICO_RESERVA (Almacenamiento en Tablespace Propio)
- **Razón:** Respaldar el requerimiento explícito de la Entrega 1 de contar con un *tablespace propio para el histórico de reservas*.
- **Rol:** Almacenar de forma segregada y optimizada las reservas de periodos anteriores o finalizadas (volumen de 25.000 reservas en 2024–2026), evitando que el crecimiento del histórico penalice el plan de ejecución y el buffer cache de las reservas activas.
- **Propiedades:**
  - `id_reserva` (NUMBER, PK): Consecutivo de la reserva archivada.
  - `id_cliente` (NUMBER, NOT NULL): Identificador del cliente titular.
  - `id_alojamiento` (NUMBER, NOT NULL): Alojamiento donde se cumplió la estadía.
  - `fecha_reserva` (TIMESTAMP, NOT NULL): Momento de creación original.
  - `fecha_checkin` (DATE, NOT NULL): Fecha de ingreso ejecutada.
  - `fecha_checkout` (DATE, NOT NULL): Fecha de salida ejecutada.
  - `estado` (VARCHAR2, NOT NULL): Estado final ('FINALIZADA', 'CANCELADA').
  - `valor_total` (NUMBER(12,2), NOT NULL): Monto total consolidado.
  - `fecha_archivado` (TIMESTAMP, NOT NULL, DEFAULT SYSTIMESTAMP): Momento en que la tupla fue transferida al tablespace histórico.
- **Análisis de normalización y almacenamiento físico:**
  - *Segregación física por Tablespace:* Se ubica explícitamente en el tablespace dedicado `TS_HISTORICO_RESERVAS` (sobre datafile independiente). Permite aplicar compresión y particionamiento por rango temporal sin afectar el espacio de transaccionalidad concurrente (`SELECT ... FOR UPDATE`).

---

## 3. Matriz Consolidada de Relaciones del Modelo Completo

| Entidad Origen | Cardinalidad | Entidad Destino | Clave Foránea / Vía | Justificación de Negocio / Conexión con diagrama-e |
| :--- | :--- | :--- | :--- | :--- |
| **USUARIO_SISTEMA** | 1 : 0..1 | **CLIENTE** | `CLIENTE.id_usuario` | Especialización *"Es un"*: el cliente es un usuario con perfil de turista. |
| **USUARIO_SISTEMA** | 1 : 0..1 | **PROPIETARIO** | `PROPIETARIO.id_usuario` | Especialización *"Es un"*: el propietario es un usuario que administra alojamientos. |
| **PROPIETARIO** | 1 : 1..N | **ALOJAMIENTO** | `ALOJAMIENTO.id_propietario` | Un propietario crea y opera uno o más alojamientos en el Quindío. |
| **MUNICIPIO** | 1 : 0..N | **ALOJAMIENTO** | `ALOJAMIENTO.id_municipio` | Ubicación geográfica dentro de los 12 municipios. |
| **TIPO_ALOJAMIENTO** | 1 : N | **ALOJAMIENTO** | `ALOJAMIENTO.id_tipo_alojamiento` | Clasificación por modalidad (finca cafetera, hotel, glamping, hostal). |
| **TIPO_HABITACION** | 1 : N | **HABITACION** | `HABITACION.id_tipo_habitacion` | **Normalización 3FN:** Estandariza aforo y tipología de habitación. |
| **ALOJAMIENTO** | 1 : 1..N | **HABITACION** | `HABITACION.id_alojamiento` | Inventario de unidades de hospedaje del establecimiento. |
| **ALOJAMIENTO** | 1 : 0..N | **ALOJAMIENTO_COMODIDAD**| `ALOJAMIENTO_COMODIDAD.id_alojamiento` | **Normalización 1FN:** Resuelve relación N:M de amenities. |
| **COMODIDAD** | 1 : 0..N | **ALOJAMIENTO_COMODIDAD**| `ALOJAMIENTO_COMODIDAD.id_comodidad` | Catálogo de amenities e instalaciones disponibles. |
| **ALOJAMIENTO** | 1 : 0..N | **SERVICIO** | `SERVICIO.id_alojamiento` | Catálogo de servicios adicionales prestados en el alojamiento. |
| **ALOJAMIENTO** | 0..1 : 0..N | **RESERVA** | `RESERVA.id_alojamiento` | Enlace directo con el alojamiento sede de la reserva. |
| **ALOJAMIENTO** | 1 : 0..N | **RESENA** | `RESENA.id_alojamiento` | Evaluaciones que referencian la reputación del alojamiento. |
| **ALOJAMIENTO** | 1 : 0..N | **LIQUIDACION_MENSUAL** | `LIQUIDACION_MENSUAL.id_alojamiento` | Persistencia del cursor de liquidación mensual por alojamiento. |
| **HABITACION** | 1 : N | **TARIFA** | `TARIFA.id_habitacion` | Parametrización de precios por habitación. |
| **TEMPORADA** | 1 : 0..N | **TARIFA** | `TARIFA.id_temporada` | Regulación temporal de los precios por temporada estacional. |
| **TARIFA** | 1 : 0..N | **AUDITORIA_TARIFA** | `AUDITORIA_TARIFA.id_tarifa` | Histórico alimentado por el disparador de sentencia de la Entrega 2. |
| **CLIENTE** | 1 : 0..N | **RESERVA** | `RESERVA.id_cliente` | Solicitudes de reservas formalizadas por el turista. |
| **CLIENTE** | 1 : 1..N | **PAGO** | `PAGO.id_cliente` | Transacciones financieras realizadas por el cliente. |
| **RESERVA** | 1 : 1..N | **PAGO** | `PAGO.id_reserva` | Desembolsos generados para cancelar o abonar a una reserva. |
| **RESERVA** | 1 : 0..N | **RESENA** | `RESENA.id_reserva` | Opinión generada a partir de la estadía realizada. |
| **RESERVA** | 1 : 1..N | **RESERVA_HABITACION** | `RESERVA_HABITACION.id_reserva` | **Referencia cruzada:** Renglones de habitaciones tomadas en la reserva. |
| **HABITACION** | 1 : 0..N | **RESERVA_HABITACION** | `RESERVA_HABITACION.id_habitacion` | Asignación física de la habitación a la reserva. |
| **RESERVA** | 1 : 0..N | **RESERVA_SERVICIO** | `RESERVA_SERVICIO.id_reserva` | **Referencia cruzada:** Servicios consumidos durante la estadía. |
| **SERVICIO** | 1 : 0..N | **RESERVA_SERVICIO** | `RESERVA_SERVICIO.id_servicio` | Servicio facturado en una o múltiples reservas. |
| **RESERVA** | 1 : 0..1 | **HISTORICO_RESERVA** | `HISTORICO_RESERVA.id_reserva` | Segregación física en tablespace propio `TS_HISTORICO_RESERVAS`. |
