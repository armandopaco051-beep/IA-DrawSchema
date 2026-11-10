# Worker local para el servicio IA desplegado

Implementado únicamente en DrawSchemaAI. No cambia frontend, backend de
diagramas ni Neon, y no crea tablas. Los agentes permanecen en el servidor;
el worker del PC solo llama a dos rutas de Ollama.

URLs actuales:

- IA: https://iabackend-copia.onrender.com
- Backend: https://backendcopia-software.onrender.com (sin `/docs`)
- Frontend: https://frontend-copia-software.vercel.app
- Ollama del PC: http://127.0.0.1:11434

## Configuración inicial

Desde la raíz de DrawSchemaAI:

```powershell
.\venv\Scripts\python.exe -m worker_local.setup
```

Genera tokens distintos para conectar el worker y para el puente interno de
los agentes. Repetir el comando conserva los tokens existentes. Produce:

- `worker_local/.env`: URL desplegada, modelo y token del PC.
- `worker_local/render.env`: variables privadas para copiar a Render.
- Añade los tokens al `.env` del proyecto y conserva `OLLAMA_TRANSPORT=direct`
  para las pruebas locales actuales.

Estos archivos privados están excluidos de Git. No copiar sus tokens al
frontend ni compartirlos. `render.env` no incluye GEMINI_API_KEY: la clave
de Gemini y sus modelos deben seguir configurados en Render.

## Servicio IA en Render

1. Publicar estos cambios en el repositorio conectado al servicio IA.
2. Copiar las variables de `worker_local/render.env` a Environment del servicio
   `iabackend-copia` y volver a desplegar.
3. Mantener UNA instancia y UN proceso Uvicorn. Comando de inicio:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --ws-max-size 2097152
```

El estado de las conexiones vive en ese proceso. Escalar a varias instancias
requiere un broker compartido; esta implementación no pretende ofrecer eso.
OLLAMA_BRIDGE_BASE_URL se deja vacío: el puente local de los agentes usa PORT
automáticamente. No debe apuntar al Ollama del PC desde Render.

El backend ya llama a https://iabackend-copia.onrender.com; no necesita rutas
nuevas. Su tiempo de espera debe dar margen al servicio IA. El frontend ya usa
esa URL para la IA y no necesita el token del worker.

## Ejecutar en el PC

Abrir Ollama, con qwen2.5-coder:1.5b descargado, y comprobar:

```powershell
cd C:\Users\Armando\DrawSchemaAI
.\venv\Scripts\python.exe -m worker_local.main --check
```

Si informa que el endpoint no existe, todavía falta desplegar la nueva versión
del servicio IA. Si informa un error de configuración, comprobar el transporte
`worker` y los tokens de Render. El modelo debe coincidir en ambos lados.

Para iniciar:

```powershell
.\venv\Scripts\python.exe -m worker_local.main
```

También se puede abrir `worker_local/iniciar-worker.cmd`. Dejarlo abierto y
detener con Ctrl+C. No necesita administrador, túnel ni abrir el puerto 11434
a Internet. El worker se conecta hacia afuera mediante WSS y se reconecta si
la conexión se interrumpe. Solo accede al Ollama de localhost y solo permite
`api/chat` y `v1/chat/completions`; no ejecuta comandos ni modifica archivos
del proyecto a petición del modelo.

## Flujo y límites

1. La web guarda la pregunta mediante el backend existente.
2. DrawSchemaAI obtiene el contexto y selecciona el agente local.
3. El relay envía la inferencia al worker disponible y correlaciona su respuesta.
4. El worker consulta Ollama y devuelve el JSON. Un heartbeat avisa si el modelo
   está instalado y disponible.
5. Los agentes construyen la propuesta. Aplicar plan conserva el ejecutor y los
   permisos existentes; el worker jamás escribe en el diagrama.

Gemini e imágenes siguen su conexión actual. Solo hay que tener el PC activo
para usar la IA local. Por PC se procesa una inferencia a la vez, con una espera
acotada de solicitudes. Sin worker disponible se informa un error inmediato.

No hay cola persistente: un reinicio o desconexión falla las inferencias en
curso y el usuario puede reintentar la pregunta que sigue guardada en Neon.
Las respuestas y prompts del relay se liberan al finalizar la inferencia.

El chat conserva su petición HTTP actual mientras espera. Este cambio no
elimina límites de espera de navegador, proxy o hosting. Para procesos largos
habrá que añadir trabajos asíncronos y consulta de estado en la aplicación.

## Verificación

Pruebas automatizadas de autenticación separada, correlación, serialización,
desconexión, cancelación, configuración y transporte de agentes; además, prueba
local real de WS → worker → Ollama tanto con API nativa como con chat OpenAI.
No confundir esa verificación local con un despliegue efectivo en Render.
