# Texto local e imágenes en Google

Configuración en `.env`:

```dotenv
AI_PROVIDER=hybrid
OLLAMA_MODEL=qwen2.5:0.5b
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_API_KEY=ollama
IMAGE_MODEL=gemini/gemini-3.5-flash-lite
IMAGE_FALLBACK_MODELS=
LITELLM_API_BASE=
```

Conservar GEMINI_API_KEY en el archivo privado, sin compartirla ni subirla al repositorio.

Instalar el modelo en PowerShell:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen2.5:0.5b
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
```

Si Ollama está apagado, abrir la aplicación o ejecutar `ollama serve` en otra terminal antes de descargar/probar.

Reiniciar DrawSchemaAI después de modificar el proveedor; los agentes se construyen al importar sus módulos.
`/health` debe indicar `proveedor=hybrid`, modelos de texto `openai/qwen2.5:0.5b` e imágenes `gemini/gemini-3.5-flash-lite`.

Texto y planes se generan localmente; imágenes se envían a Google con la clave existente. No se usa el modelo de texto para leer imágenes ni se envían consultas de texto a Gemini como respaldo. El generador determinista de Spring Boot conserva su comportamiento actual.

0.5B es un modelo pequeño: es necesario evaluar respuestas en español, atribución de autores, reglas UML y JSON de acciones con casos reales. No se garantiza la misma calidad que con modelos mayores. Las validaciones y los permisos existentes siguen siendo obligatorios.

Para producción, el servicio IA desplegado necesitará una conexión protegida al Ollama de la computadora; localhost en Render no apunta al equipo del usuario. El historial en Neon y el análisis de imágenes en Gemini necesitan Internet.


## Selección por consulta desde la interfaz

El panel ofrece Gemini o Local para texto, independientemente del selector Individual/Grupal. La preferencia se conserva en ese navegador. El frontend envía text_provider=gemini o text_provider=local al backend; este lo reenvía a /ai/planner. La elección está aislada por contexto de petición, sin modificar el proveedor de otros usuarios. Cada agente se construye con la configuración vigente de esa petición.

Las imágenes van SIEMPRE a Gemini, incluso cuando el texto usa Local. El resultado guardado identifica provider y model. Un reintento de una consulta con respuesta existente devuelve esa misma respuesta; para comparar proveedores, enviar una consulta nueva. No hay respaldo automático entre proveedores.

Modelo local preparado: qwen2.5-coder:1.5b. Ollama debe estar abierto. Cambiar de proveedor en el selector no instala modelos ni inicia programas en la computadora.

Reiniciar backend y DrawSchemaAI después de actualizar código. No se necesitan columnas nuevas en Neon: la procedencia se guarda en resultado_ia.
