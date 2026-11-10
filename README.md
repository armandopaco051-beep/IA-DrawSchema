# DrawSchemaAI — IA híbrida y worker local

Servicio de inteligencia artificial de DrawSchema para interpretar consultas,
proponer cambios en diagramas UML, sugerir mejoras, validar modelos y generar
código. Permite seleccionar Gemini o un modelo local de Ollama para texto.
El análisis de imágenes permanece en Gemini.

Este documento describe especialmente la integración del **worker local**,
sus archivos, configuración, despliegue y cinco historias de usuario.

## 1. Objetivo

Permitir que la aplicación publicada utilice el modelo instalado en la
computadora del administrador. Los agentes permanecen en el servicio IA
desplegado; el worker ejecuta las inferencias en Ollama y devuelve el resultado.

El worker no guarda diagramas, no aplica planes y no ejecuta código generado
por el modelo. La modificación del diagrama conserva el flujo existente de
permisos, validación y **Aplicar plan**.

## 2. Componentes y direcciones configuradas

| Componente | Ubicación | Responsabilidad |
| --- | --- | --- |
| Frontend | https://frontend-copia-software.vercel.app | Chat, editor y revisión de planes. |
| Backend principal | https://backendcopia-software.onrender.com | Usuarios, proyectos, conversaciones, diagramas y permisos. |
| Servicio IA | https://iabackend-copia.onrender.com | Contexto, agentes y coordinación del worker. |
| Base de datos existente | Neon | Persistencia gestionada por el backend principal. |
| Worker | Computadora con Ollama | Recibir inferencias y devolver sus respuestas. |
| Ollama | http://127.0.0.1:11434, en el PC | Ejecutar el modelo local. |

La URL del backend se utiliza sin `/docs`: esa ruta corresponde a la
documentación de la API, no a su dirección base.

Las direcciones indican la configuración del proyecto; no garantizan que la
última versión del código esté publicada ni disponible en esos servicios.

## 3. Arquitectura y recorrido de una consulta

```text
Usuario en la aplicación publicada
                |
                v
Backend principal: guarda la consulta y valida el acceso
                |
                v
DrawSchemaAI: obtiene contexto y selecciona el proveedor
                |
        +-------+--------------------+
        |                            |
        v                            v
      Gemini                    Agentes locales
        |                            |
        |                     Relay en el servidor
        |                            |
        |                      WebSocket seguro
        |                            |
        |                       Worker del PC
        |                            |
        |                          Ollama
        |                            |
        +--------- respuesta --------+
                      |
                      v
           Construcción y validación del plan
                      |
                      v
          Usuario revisa y pulsa Aplicar plan
                      |
                      v
            Backend actualiza el diagrama
```

1. La web envía la consulta y el backend la conserva en el historial existente.
2. DrawSchemaAI recibe el contexto del usuario, proyecto y diagrama activo.
3. Si se seleccionó Gemini, utiliza su conexión habitual.
4. Si se seleccionó IA local en modo worker, el relay busca una conexión
   disponible para el modelo configurado.
5. Asigna un identificador a la inferencia y la envía al PC.
6. El worker consulta Ollama en localhost y devuelve el JSON con ese identificador.
7. El servicio IA entrega la respuesta al agente que la solicitó.
8. Los agentes preparan el resultado. Una consulta conceptual no requiere
   acciones; una modificación se presenta como plan para revisar y aplicar.

La conexión hacia Render la inicia el PC. No requiere abrir el puerto 11434
a Internet ni publicar Ollama mediante un túnel.

## 4. Modos de conexión

| Valor de `OLLAMA_TRANSPORT` | Funcionamiento | Uso |
| --- | --- | --- |
| `direct` | DrawSchemaAI llama directamente a `OLLAMA_BASE_URL`. | Desarrollo con IA y Ollama accesibles desde el mismo entorno. |
| `worker` | El servicio IA utiliza el worker conectado por WebSocket. | Servicio desplegado con Ollama ejecutándose en el PC. |

En Render, `localhost` no representa la computadora del usuario. El puente
interno de los agentes sí usa localhost deliberadamente: apunta al propio
servidor IA y luego deriva la inferencia por WebSocket hacia el PC.

Gemini y las imágenes conservan su conexión habitual en ambos modos.

## 5. Archivos y responsabilidades

### 5.1. Archivos nuevos del servicio IA

| Archivo | Responsabilidad |
| --- | --- |
| `app/services/worker_relay.py` | Gestiona workers conectados, disponibilidad, espera, correlación de respuestas y cancelaciones. |
| `app/routers/local_worker.py` | Define las rutas de conexión, estado y puente; valida autenticación y protocolo. |
| `app/providers/ollama_connection.py` | Selecciona transporte directo o worker para las llamadas a Ollama. |
| `app/routers/__init__.py` | Permite importar la carpeta como paquete Python. |

El relay incluye `WorkerConnection`, que representa una conexión del PC, y
`WorkerRelay`, que coordina las solicitudes. `register()` y `remove()`
administran conexiones; `active()` comprueba disponibilidad; `infer()` envía
una consulta y espera; `receive()` resuelve la respuesta correspondiente.

### 5.2. Archivos del PC

| Archivo | Responsabilidad |
| --- | --- |
| `worker_local/main.py` | Cliente WebSocket: comprueba Ollama, recibe trabajos, ejecuta inferencias, envía heartbeat y reconecta. |
| `worker_local/setup.py` | Genera la configuración y los secretos locales sin mostrarlos en consola. |
| `worker_local/iniciar-worker.cmd` | Inicia el worker desde Windows usando el entorno virtual del proyecto. |
| `worker_local/requirements.txt` | Dependencias del cliente local. |
| `worker_local/.env.example` | Plantilla pública de configuración del PC. |
| `worker_local/__init__.py` | Permite iniciar el cliente mediante `python -m worker_local.main`. |

En `main.py`, `local_ready()` comprueba que el modelo esté instalado;
`run_inference()` llama a Ollama; `connected_session()` gestiona mensajes y
cancelaciones; `run()` mantiene la conexión; `check()` realiza el diagnóstico.

### 5.3. Archivos existentes adaptados

| Archivo | Cambio relacionado con el worker |
| --- | --- |
| `app/config/settings.py` | Añade el modo de transporte, tokens y límites de espera/disponibilidad. |
| `app/config/agents_models.py` | Obtiene la URL y autenticación apropiadas para los agentes locales. |
| `app/providers/ai_provider.py` | Valida que el modo worker tenga sus secretos configurados. |
| `app/agents/local/interpreter.py` | Utiliza la conexión común en sus llamadas nativas de inferencia. |
| `app/main.py` | Registra las rutas nuevas y comunica errores del worker. |
| `.gitignore` | Excluye configuración privada y el export de variables para Render. |
| `.env.example` | Documenta las variables públicas de ejemplo. |

Los agentes locales de planificación, sugerencias, validación y generación
siguen separados de los agentes Gemini. Más información en
[Agentes por proveedor](docs/model-instructions.md).

### 5.4. Archivos de configuración privados

| Archivo | Contenido y uso |
| --- | --- |
| `.env` | Configuración del servicio IA en desarrollo; conserva el modo directo cuando no estaba definido. |
| `worker_local/.env` | URL del servicio desplegado, token del worker y modelo del PC. |
| `worker_local/render.env` | Variables que deben añadirse al servicio IA en Render. |

Estos archivos no deben subirse a Git ni incorporarse al frontend.
`render.env` no contiene la clave de Gemini: conservar las variables Gemini
que ya estén configuradas en Render.

## 6. Historias de usuario del worker

Se documentan **cinco historias funcionales**. Los archivos, heartbeat y
reconexión son componentes o tareas técnicas de esas historias, no historias
adicionales por sí solos.

### HU-01 — Utilizar IA local desde la aplicación desplegada

**Como** usuario de DrawSchema, **quiero** consultar la IA local desde la
aplicación publicada, **para** obtener explicaciones y planes de modificación
del diagrama usando el modelo instalado en el PC conectado.

**Prioridad:** alta.

**Criterios de aceptación:**

- Al seleccionar IA local, la inferencia utiliza un worker disponible para el modelo configurado.
- La respuesta mantiene el formato esperado por el agente y el chat.
- Los planes conservan la revisión y ejecución mediante Aplicar plan y sus permisos existentes.
- Gemini sigue disponible mediante su conexión actual.

**Tareas técnicas:** adaptar el transporte nativo y compatible con OpenAI;
integrar el relay con los agentes y el manejo de errores.

### HU-02 — Conectar el PC que ejecuta Ollama

**Como** administrador, **quiero** conectar mi computadora con el servicio IA,
**para** procesar las inferencias mediante el Ollama local.

**Prioridad:** alta.

**Criterios de aceptación:**

- El worker se conecta a la URL configurada mediante WSS en el despliegue público.
- Verifica la disponibilidad del modelo en Ollama.
- Envía señales periódicas de actividad y disponibilidad.
- Puede iniciarse desde terminal o mediante el archivo de inicio de Windows.

**Tareas técnicas:** cliente WebSocket, configuración del PC, comprobación del
modelo y comando de diagnóstico.

### HU-03 — Recibir la respuesta de la consulta correspondiente

**Como** usuario, **quiero** recibir la respuesta de mi propia consulta aunque
otros usuarios utilicen la IA, **para** evitar que se mezclen las respuestas.

**Prioridad:** alta.

**Criterios de aceptación:**

- Cada inferencia tiene un identificador único.
- El relay entrega el resultado únicamente a la solicitud que espera ese identificador.
- Un PC procesa una inferencia a la vez y la espera de otras solicitudes es acotada.
- Una respuesta tardía de una solicitud cancelada no resuelve otra consulta.

**Tareas técnicas:** correlación mediante identificadores, exclusión de ejecución
simultánea por PC y limpieza de solicitudes pendientes.

### HU-04 — Gestionar desconexiones y reintentos

**Como** usuario, **quiero** recibir un aviso cuando la IA local no esté
disponible y poder reintentar, **para** continuar sin perder mi consulta guardada.

**Prioridad:** alta.

**Criterios de aceptación:**

- Sin worker disponible, el servicio devuelve un error comprensible.
- La espera termina al agotarse el tiempo configurado.
- La desconexión falla las inferencias afectadas en lugar de dejarlas esperando indefinidamente.
- El cliente intenta reconectar con esperas crecientes.
- La consulta conserva el historial gestionado por el backend y puede reintentarse.

**Tareas técnicas:** control de tiempo, cancelación, reconexión y propagación de
errores. Reconectar el canal no aplica automáticamente un plan anterior.

### HU-05 — Autorizar solamente conexiones válidas

**Como** administrador, **quiero** autenticar el worker y el puente interno,
**para** impedir que procesos no autorizados utilicen el Ollama del PC.

**Prioridad:** alta.

**Criterios de aceptación:**

- Un token autoriza al worker y otro distinto autoriza al puente de los agentes.
- Las rutas rechazan tokens ausentes o incorrectos.
- Los secretos no se incluyen en el frontend ni en Git.
- El worker solo llama al Ollama de localhost y a las rutas permitidas.
- El worker no ejecuta comandos ni código generado por el modelo.

**Tareas técnicas:** generación y validación de secretos, control de destinos,
límites de tamaño y exclusión de archivos privados.

## 7. Configuración y ejecución

### 7.1. Requisitos

- Python y entorno virtual del proyecto. `.python-version` define Python 3.13.
- Dependencias instaladas desde `requirements.txt` para el servicio IA.
- Ollama instalado y abierto en el PC.
- Modelo `qwen2.5-coder:1.5b` descargado, o el mismo modelo local configurado en ambos extremos.
- Acceso al servicio IA de Render para publicar el código y configurar sus variables.

Si todavía no existe un entorno virtual, desde la raíz del repositorio:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

El cliente local también dispone de su listado mínimo en
`worker_local/requirements.txt`; las dependencias de ese cliente ya están
incluidas en las del proyecto completo.

### 7.2. Preparar la configuración

Desde la raíz:

```powershell
cd C:\Users\Armando\DrawSchemaAI
.\venv\Scripts\python.exe -m worker_local.setup
```

Este comando genera los archivos privados descritos anteriormente. Repetirlo
conserva los tokens existentes; no despliega el código ni configura Render
automáticamente. Tampoco instala Ollama ni descarga el modelo.

Para otra dirección de servicio:

```powershell
.\venv\Scripts\python.exe -m worker_local.setup --server-url https://tu-servicio-ia.onrender.com
```

### 7.3. Configurar Render

1. Publicar los cambios en el repositorio conectado al servicio IA.
2. Añadir a Environment las variables de `worker_local/render.env`.
3. Conservar las variables existentes de Gemini.
4. Configurar una instancia y un proceso Uvicorn.
5. Volver a desplegar.

Comando de inicio:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --ws-max-size 2097152
```

### 7.4. Comprobar Ollama

En Windows, si el ejecutable no está disponible mediante PATH:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
```

Para descargar el modelo, con Ollama ya ejecutándose:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen2.5-coder:1.5b
```

Si Ollama no está abierto, iniciarlo desde su aplicación o ejecutar en otra
terminal:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
```

No iniciar otra instancia de `serve` si Ollama ya está escuchando en ese puerto.

### 7.5. Diagnosticar e iniciar el worker

```powershell
.\venv\Scripts\python.exe -m worker_local.main --check
```

Después:

```powershell
.\venv\Scripts\python.exe -m worker_local.main
```

También se puede abrir `worker_local/iniciar-worker.cmd`. Mantener el proceso
abierto mientras se utilice la IA local. Se detiene con `Ctrl+C`.

No se configuró inicio automático con Windows.

## 8. Variables principales

| Variable | Ubicación | Función |
| --- | --- | --- |
| `OLLAMA_TRANSPORT` | Servicio IA | Selecciona `direct` o `worker`. |
| `OLLAMA_WORKER_TOKEN` | Servicio IA y PC | Autoriza la conexión del worker. Debe coincidir en ambos. |
| `OLLAMA_BRIDGE_TOKEN` | Servicio IA | Autoriza el puente interno; debe ser distinto del token del worker. |
| `OLLAMA_MODEL` | Servicio IA y PC | Modelo local; debe coincidir en ambos extremos. |
| `WORKER_SERVER_URL` | PC | URL HTTPS del servicio IA desplegado. |
| `OLLAMA_URL` | PC | Dirección local de Ollama, normalmente `http://127.0.0.1:11434`. |
| `WORKER_ID` | PC | Identifica al worker; por defecto deriva del nombre de la computadora. |
| `WORKER_HEARTBEAT_SECONDS` | PC | Intervalo de comprobación; valor por defecto: 10 segundos. |
| `WORKER_INFERENCE_TIMEOUT` | PC | Tiempo de espera para Ollama; valor por defecto: 540 segundos. |
| `OLLAMA_WORKER_STALE_SECONDS` | Servicio IA | Vigencia del último mensaje recibido; valor por defecto: 45 segundos. |
| `OLLAMA_WORKER_MAX_PENDING` | Servicio IA | Máximo por conexión, incluyendo la solicitud activa; valor por defecto: 8. |
| `AI_REQUEST_TIMEOUT` | Servicio IA | Tiempo máximo de inferencia; el export para Render propone 600 segundos. |
| `OLLAMA_BRIDGE_BASE_URL` | Servicio IA | Normalmente vacío; el puente calcula su URL interna usando `PORT`. |

Los límites de espera del backend y del hosting también deben dar margen al
servicio IA. Aumentar una sola variable no elimina los límites de los demás componentes.

## 9. Rutas y protocolo

| Ruta | Tipo | Autenticación | Función |
| --- | --- | --- | --- |
| `/internal/worker/connect` | WebSocket | Token del worker | Canal del PC hacia el servicio IA. |
| `/internal/worker/status` | GET | Token del worker | Estado de las conexiones registradas. |
| `/internal/ollama/{path}` | POST | Token del puente | Compatibilidad con las llamadas de los agentes. |

Las únicas rutas de Ollama permitidas son `api/chat` y
`v1/chat/completions`. No se admite streaming en este transporte.

| Mensaje | Dirección | Uso |
| --- | --- | --- |
| `hello` | PC → servidor | Presenta identificador, modelo y disponibilidad. |
| `welcome` | Servidor → PC | Confirma el registro del worker. |
| `heartbeat` | PC → servidor | Actualiza la disponibilidad. |
| `infer` | Servidor → PC | Envía una consulta identificada. |
| `result` | PC → servidor | Devuelve el JSON o un código de error. |
| `cancel` | Servidor → PC | Solicita cancelar una inferencia que ya no se espera. |

## 10. Pruebas y estado de verificación

Ejecutar:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -q
```

En la verificación realizada pasaron **112 pruebas**, incluyendo las del
proyecto previo y las nuevas del worker. Se comprobaron autenticación,
correlación, ejecución serial, desconexión, cancelación, configuración privada
y conservación de la conexión Gemini.

También se realizó una prueba local real del circuito
**WebSocket → worker → Ollama**, tanto con la API nativa como con la compatible
con OpenAI. Ambas devolvieron HTTP 200 y la respuesta de prueba `OK`.

El código y las historias están implementados para validación. La aceptación
integrada en la aplicación publicada requiere desplegar esta versión, copiar
las variables correctas y probar desde el navegador. La comprobación remota
realizada no respondió dentro del plazo, por lo que no se considera verificada
la conexión de producción.

## 11. Limitaciones y recuperación

- El PC debe permanecer encendido, conectado a Internet y con Ollama y el worker activos.
- Esta versión utiliza una instancia y un proceso del servicio IA. Escalar a
  varios procesos requiere compartir el estado mediante un broker externo.
- El relay conserva solo solicitudes en curso en memoria; no es una cola persistente en Neon.
- Reiniciar el servicio o desconectar el PC interrumpe las inferencias afectadas.
  El historial existente permite al usuario reintentar su consulta.
- La reconexión restaura el canal; no aplica cambios ni reproduce automáticamente planes anteriores.
- Los mensajes de inferencia tienen un límite de 2 MB.
- El chat mantiene la espera HTTP existente. Para trabajos prolongados habría
  que incorporar envío asíncrono y consulta de estado en la aplicación.
- La calidad y velocidad de las respuestas dependen del modelo y del hardware.
  Tener un worker no garantiza la misma precisión que Gemini.

## 12. Solución de problemas

| Situación | Comprobación |
| --- | --- |
| El endpoint del worker devuelve 404. | Publicar y desplegar la nueva versión de DrawSchemaAI. |
| Aparece 401 o se rechaza la conexión. | Revisar que el token del PC coincida con Render y que se use el token correcto para cada ruta. |
| Aparece un error de configuración 503. | Configurar `OLLAMA_TRANSPORT=worker` y los dos secretos distintos en el servidor. |
| Ollama o el modelo no están disponibles. | Abrir Ollama y verificar el modelo con `ollama list`. |
| El servidor rechaza el modelo. | Igualar `OLLAMA_MODEL` en Render y en `worker_local/.env`. |
| El servicio desplegado no responde. | Revisar URL, estado del despliegue y registros de Render; después repetir `--check`. |
| La consulta agota el tiempo. | Comprobar el PC y los límites de espera; dividir solicitudes grandes cuando sea necesario. |
| Algunas peticiones no encuentran al worker. | Comprobar que haya una sola instancia y un solo proceso Uvicorn. |

## 13. Documentación complementaria

- [Guía operativa del worker](docs/worker-local.md).
- [Agentes e instrucciones por proveedor](docs/model-instructions.md).
- [Configuración híbrida](docs/hybrid-provider.md).

Esta integración se implementó en **DrawSchemaAI**. No requirió añadir tablas
de worker a Neon ni modificar el frontend o el backend principal.

## 14. Casos de uso del worker

Se identifican **cinco casos de uso** para esta integración. Las historias de
usuario expresan necesidades; los casos de uso describen la interacción con
el sistema para satisfacerlas. No existe una correspondencia obligatoria de
una historia por caso de uso.

### 14.1. Actores y alcance

| Actor | Participación |
| --- | --- |
| Usuario de DrawSchema | Consulta la IA desde la aplicación y reintenta solicitudes guardadas. |
| Administrador u operador | Configura el servicio IA y ejecuta el worker en el PC. Es una responsabilidad operativa; no implica crear un nuevo rol en la base de datos. |
| Backend principal | Sistema externo a DrawSchemaAI que valida acceso, aporta contexto y conserva las conversaciones. |
| Ollama | Sistema externo que ejecuta la inferencia en la computadora del operador. |

El sistema documentado comprende el servicio DrawSchemaAI y su cliente
`worker_local`. Heartbeat, autenticación, correlación y reconexión son
comportamientos internos o transversales de los casos de uso. Aplicar un plan
al diagrama pertenece al flujo existente de edición y no se cuenta aquí como
un caso nuevo del worker.

### 14.2. Resumen y trazabilidad

| Código | Caso de uso | Actor principal | Historias relacionadas |
| --- | --- | --- | --- |
| CU-01 | Configurar la conexión del worker | Administrador | HU-02, HU-05 |
| CU-02 | Conectar el worker con el servicio IA | Administrador | HU-02, HU-05 |
| CU-03 | Consultar la IA local desde la aplicación publicada | Usuario | HU-01, HU-03, HU-05 |
| CU-04 | Comprobar la disponibilidad de la IA local | Administrador | HU-02, HU-04 |
| CU-05 | Reintentar una consulta interrumpida | Usuario | HU-01, HU-04 |

### CU-01 — Configurar la conexión del worker

**Actor principal:** administrador u operador.

**Objetivo:** preparar direcciones, modelo y credenciales para conectar el PC
con el servicio IA desplegado.

**Precondiciones:** disponer del proyecto y sus dependencias; tener acceso a
las variables del servicio IA en Render.

**Disparador:** el administrador necesita habilitar el transporte worker.

**Flujo principal:**

1. El administrador ejecuta `python -m worker_local.setup` desde el entorno del proyecto.
2. El sistema lee la configuración existente y genera los secretos que falten.
3. Guarda la configuración del PC y el export privado para Render.
4. El administrador añade las variables del export al servicio IA, conservando las de Gemini.
5. Publica el código y despliega el servicio con una instancia y un proceso Uvicorn.

**Alternativas y errores:**

- Si ya existen secretos válidos, el sistema los conserva al repetir la configuración.
- Si los secretos son iguales o demasiado cortos, se rechaza la configuración.
- Si cambia la URL pública, el administrador utiliza `--server-url`.
- La configuración local no publica automáticamente cambios ni variables en Render.

**Postcondición:** quedan preparados los archivos locales y la configuración
del servicio desplegado para utilizar el worker. Este caso no inicia la
conexión permanente ni ejecuta una inferencia.

### CU-02 — Conectar el worker con el servicio IA

**Actor principal:** administrador u operador.

**Actor de apoyo:** Ollama.

**Objetivo:** habilitar el PC como proveedor de inferencias locales para los agentes.

**Precondiciones:** CU-01 completado; servicio IA desplegado con modo worker;
Ollama abierto y modelo configurado instalado en el PC.

**Disparador:** el administrador ejecuta `python -m worker_local.main` o abre
`iniciar-worker.cmd`.

**Flujo principal:**

1. El worker carga y valida su configuración.
2. Inicia una conexión WSS saliente al servicio IA usando el token del worker.
3. Comprueba el modelo local y envía su presentación con identificador y disponibilidad.
4. El servidor valida autenticación, protocolo y coincidencia del modelo.
5. Registra la conexión y confirma su aceptación.
6. El worker mantiene el canal y envía señales periódicas de disponibilidad.

**Alternativas y errores:**

- Un token incorrecto o un modelo distinto provocan el rechazo de la conexión.
- Si Ollama está apagado, el worker puede permanecer conectado, pero informa que no está listo para inferencias.
- Si el canal se interrumpe, el cliente intenta reconectar con esperas crecientes.
- Si el administrador pulsa `Ctrl+C`, el worker se detiene.

**Postcondición:** el servidor conoce la conexión y su disponibilidad. Las
consultas pueden utilizarla mientras siga activa y el modelo esté listo.

### CU-03 — Consultar la IA local desde la aplicación publicada

**Actor principal:** usuario de DrawSchema.

**Actores de apoyo:** backend principal y Ollama.

**Objetivo:** obtener una respuesta o un plan usando el modelo del PC conectado.

**Precondiciones:** usuario con acceso al proyecto o conversación; proveedor
local seleccionado; servicio IA y worker disponibles. Para modificar el
diagrama se conservan los permisos de edición del flujo existente.

**Disparador:** el usuario envía una consulta dirigida a la IA.

**Flujo principal:**

1. La aplicación envía el mensaje y el backend conserva la consulta.
2. El backend solicita la respuesta a DrawSchemaAI con el contexto autorizado.
3. El agente prepara la inferencia necesaria.
4. El relay asigna un identificador y espera turno en una conexión disponible.
5. El worker recibe la inferencia y consulta Ollama en localhost.
6. Devuelve el resultado con el mismo identificador.
7. El relay entrega la respuesta al agente que la solicitó y libera la solicitud pendiente.
8. Los agentes preparan la explicación, sugerencia, validación o plan correspondiente.
9. El backend guarda la respuesta y la aplicación la presenta al usuario.

**Alternativas y errores:**

- Si hay solicitudes simultáneas, cada una mantiene su identificador y el PC las procesa de una en una.
- Si no hay worker disponible, se informa el fallo sin esperar una inferencia inexistente.
- Si la respuesta es inválida, se agota el tiempo o se pierde el canal, se informa el error y queda disponible CU-05.
- Una consulta conceptual termina con una explicación, sin acciones de modificación.

**Postcondición:** el usuario recibe su respuesta o un aviso de fallo. Un plan
propuesto todavía requiere el flujo existente de revisión y aplicación; el
worker no modifica el diagrama.

### CU-04 — Comprobar la disponibilidad de la IA local

**Actor principal:** administrador u operador.

**Actor de apoyo:** Ollama.

**Objetivo:** identificar problemas de instalación, configuración o despliegue.

**Precondiciones:** configuración local generada y entorno Python disponible.

**Disparador:** el administrador ejecuta `python -m worker_local.main --check`.

**Flujo principal:**

1. El cliente comprueba si Ollama responde y tiene el modelo instalado.
2. Consulta el estado del worker en el servicio IA usando su token.
3. Informa la URL del servicio, el modelo configurado y la cantidad de workers conectados.
4. El administrador verifica si necesita iniciar el worker o corregir la configuración.

**Alternativas y errores:**

- Si la ruta devuelve 404, se informa que falta desplegar la versión con soporte de worker.
- Si hay error de autenticación o configuración, se indica revisar tokens y modo de transporte.
- Si el servicio remoto no responde, se indica revisar el despliegue y repetir la comprobación.
- Puede haber cero workers conectados antes de ejecutar CU-02; el diagnóstico no inicia uno automáticamente.

**Postcondición:** el administrador conoce el resultado del diagnóstico sin
haber modificado diagramas ni enviado una inferencia de usuario.

### CU-05 — Reintentar una consulta interrumpida

**Actor principal:** usuario de DrawSchema.

**Actores de apoyo:** backend principal y Ollama.

**Objetivo:** obtener la respuesta de una consulta previamente guardada que no
pudo completarse por indisponibilidad o interrupción de la IA.

**Precondiciones:** consulta guardada sin respuesta satisfactoria; usuario con
acceso a esa conversación. El worker debe volver a estar disponible para
completar el reintento con IA local.

**Disparador:** el usuario pulsa la opción de obtener o reintentar la respuesta IA.

**Flujo principal:**

1. El usuario identifica la consulta pendiente en su conversación.
2. Solicita nuevamente la respuesta de ese mensaje.
3. El backend valida su acceso y reutiliza la consulta guardada.
4. El sistema vuelve a realizar la inferencia mediante CU-03.
5. Si termina correctamente, el backend conserva la respuesta y la muestra en la conversación.

**Alternativas y errores:**

- Si el worker sigue desconectado, se informa el fallo y se conserva la consulta.
- Si ya hay una respuesta guardada para el mensaje, el flujo existente puede devolverla sin generar otra.
- Si cambió el acceso a la conversación o el contexto solicitado no corresponde, se rechaza el reintento.

**Postcondición:** la consulta obtiene respuesta o permanece disponible para
un reintento posterior. No se aplica automáticamente un plan generado en un intento anterior.

### 14.3. Estado de los casos de uso

Los comportamientos descritos tienen implementación y pruebas locales. La
aceptación de los casos que involucran Render requiere verificar el despliegue
y la configuración pública. No se consideran cerrados únicamente por tener
archivos de código o pruebas unitarias.
