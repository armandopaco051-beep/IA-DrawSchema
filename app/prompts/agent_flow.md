# Flujo de agentes DrawSchemaAI

## Regla principal

La IA no escribe directo en PostgreSQL.
La IA interpreta el mensaje del usuario y propone acciones.
El backend principal valida permisos, reglas UML y persistencia.

## Configuracion de modelos

Cada agente puede usar un modelo diferente desde `.env`.

- `PLANNER_MODEL`
- `DIAGRAM_MODEL`
- `SUGGESTION_MODEL`
- `VALIDATION_MODEL`
- `CODEGEN_MODEL`

El archivo `app/config/agents_models.py` centraliza esa configuracion.
El archivo `app/providers/ai_provider.py` centraliza el proveedor de IA.

## Planner Agent

Responsabilidad:
- Convertir una solicitud del usuario en un plan ordenado.
- Leer contexto de proyecto o diagrama si se envia `proyecto_id` o `diagrama_id`.
- No ejecutar cambios todavia.

Validaciones:
- Mensaje no vacio.
- Acciones limitadas a tools conocidas.
- Acciones destructivas requieren confirmacion.
- Si falta informacion, devuelve preguntas y `can_execute=false`.

Salida:
- `intent`
- `summary`
- `actions`
- `questions`
- `can_execute`

## Diagram Agent

Responsabilidad futura:
- Ejecutar el plan aprobado usando endpoints del backend principal.

Validaciones:
- Token presente.
- El backend principal valida permisos.
- No modificar JSONB directamente.

## Suggestion Agent

Responsabilidad futura:
- Sugerir mejoras al diagrama sin aplicarlas directamente.

## Validation Agent

Responsabilidad futura:
- Revisar calidad del modelo y detectar problemas de diseno.
- No reemplaza las validaciones deterministas del backend principal.

## Codegen Agent

Responsabilidad futura:
- Generar codigo desde el JSONB validado del diagrama.
- Debe trabajar sobre una copia/artefacto, no sobre la base directamente.
