# Agentes separados por proveedor

Gemini conserva sus agentes en `app/agents/planner_agent.py`,
`suggestion_agent.py`, `validation_agent.py` y `codegen_agent.py`.
Sus reglas están en cada agente y en `app/prompts/gemini_rules.py`.

Ollama tiene agentes independientes en `app/agents/local/`:

- `planner_agent.py`: planifica y revisa que la propuesta corresponda a la petición.
- `suggestion_agent.py`: sugiere mejoras del diagrama actual.
- `validation_agent.py`: revisa la calidad del diagrama.
- `codegen_agent.py`: genera código desde el diagrama.
- `context.py`: construye la entrada compacta exclusivamente local.
- `rules.py`: reglas locales de identidad, contexto y relaciones.

Cada agente local declara sus propias INSTRUCTIONS, crea su propia instancia
Agent y configura sus parámetros. No importa prompts ni agentes de Gemini.
Puedes ajustar las instrucciones locales sin modificar Gemini.
El antiguo selector de perfiles compartidos model_profiles.py fue eliminado.

Las funciones públicas existentes despachan al conjunto local cuando el
proveedor seleccionado es local. Con Gemini ejecutan los agentes existentes.
El proveedor se conserva por solicitud, incluidos los reintentos locales.
Se mantienen los esquemas de respuesta, las comprobaciones de planes, los
permisos y el ejecutor determinista de cambios para conservar la integración
con el frontend y backend. Separar agentes no exige duplicar estos contratos.
Las imágenes siguen siendo analizadas por Gemini.

Reinicia el servicio FastAPI si no utilizas autoreload. En el chat selecciona
IA local. Prueba crear Cliente, aplicar el plan, crear Producto y aplicar el
nuevo plan. Después pide una relación con multiplicidades explícitas.
Repite con Gemini, en otro diagrama y con dos usuarios del chat grupal.

Las pruebas automáticas verifican el despacho a cada conjunto, aislamiento
entre proveedores concurrentes, independencia de instrucciones y contexto.
No verifican la precisión del modelo real. Un modelo pequeño puede necesitar
aclaraciones o no resolver planes complejos.

## Planificador local con interpretación y construcción separadas

El chat sigue usando run_planner, pero Ollama ya no debe escribir las acciones
completas del editor. interpreter.py consulta /api/chat con un esquema reducido
según la operación; commands.py define el contrato. plan_builder.py resuelve
nombres e IDs, ordena dependencias, crea/reutiliza clases de asociación y mezcla
atributos/métodos sin borrar los existentes. La extracción de relaciones usa
solo nombres actuales y petición; la ruta general conserva el contexto y el
historial compacto para solicitudes más complejas.

El resultado conserva PlannerResponse y se aplica mediante el mismo ejecutor
existente. No se aplica automáticamente y no hay fallback oculto a Gemini.
Las sugerencias, validación y generación siguen en sus agentes locales propios.

OLLAMA_CONTEXT_SIZE=8192 y OLLAMA_PLAN_TOKENS=1536 son configurables. Las
relaciones simples limitan la extracción a 384 tokens. Para diagramas grandes
puede ser necesario ampliar el contexto; una interpretación inválida o truncada
no se debe presentar como un plan aplicable.

Pruebas reales en el modelo instalado qwen2.5-coder:1.5b, con diagramas sintéticos:
- Producto/Venta con DetalleVenta: plan aplicable, creación antes del vínculo.
- Estudiante/Materia con Inscripcion: mismo comportamiento con otros nombres.
- Atributo nombre en Paciente: conserva id existente.
- Composición Pedido/DetallePedido y herencia Administrador/Usuario: tipos y
  direcciones correctos en las peticiones probadas.
- Consulta sobre clave foránea: explicación sin acciones.

Estas pruebas no escriben datos del usuario ni demuestran precisión equivalente
a Gemini en cualquier petición. La integración del compilador con el ejecutor
se verifica con un backend simulado; falta comprobar el circuito autenticado
en el navegador del usuario.
