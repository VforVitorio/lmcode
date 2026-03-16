# Design Document (internal)

Architecture decisions, agent design, and multi-agent patterns for lmcode.

---

## 1. MVP — qué construir primero y en qué orden

### Qué entra en el MVP

Un único criterio: ¿funciona `lmcode chat` en un repo real y hace algo útil?

**Entra:**
- Conexión a LM Studio (SDK oficial)
- Agent loop con tool calling
- 4 tools: `read_file`, `write_file`, `run_shell`, `search_code`
- Streaming de output en tiempo real
- Session recording (JSONL)
- `lmcode chat` y `lmcode run "<tarea>"`
- `LMCODE.md` leído e inyectado en el system prompt

**NO entra en MVP:**
- MCP / OpenAPI (v0.2)
- Plugin system (v0.2)
- Session viewer TUI (v0.3)
- Git tools (v0.2)
- Embeddings / búsqueda semántica (v0.4)
- Subagentes (v1.0)

### Orden de build

```
Día 1
  1. pyproject.toml + uv sync + estructura de carpetas    (~30 min)
  2. config/settings.py + config/paths.py                 (~30 min)
  3. tools/base.py + tools/registry.py                    (~45 min)
  4. tools/filesystem.py + tools/shell.py + tools/search  (~1.5h)

Día 2
  5. agent/memory.py — leer LMCODE.md                     (~30 min)
  6. agent/context.py — construir el system prompt        (~45 min)
  7. agent/core.py — el agent loop                        (~2h)

Día 3
  8. session/models.py + session/recorder.py              (~1h)
  9. cli/app.py + cli/chat.py                             (~1.5h)
 10. tests básicos + CI                                   (~1h)
```

Al final del día 3: `lmcode chat` funciona end-to-end.

---

## 2. El agent loop — diseño core

### Opción A: usar `model.act()` del SDK (recomendado para MVP)

```python
# agent/core.py

async def run(self, task: str) -> AgentResult:
    chat = lms.Chat(self._build_system_prompt())
    chat.add_user_message(task)

    result = await self.model.act(
        chat,
        tools=self.tool_registry.get_all(),
        on_message=self._on_message,          # stream + record
        max_prediction_rounds=self.config.max_rounds,
    )
    return AgentResult(chat=chat, result=result)
```

El SDK ya implementa el loop completo:
```
prompt → LLM → tool call? → execute → append result → repeat → done
```

Nosotros solo añadimos encima:
- Plugin hooks (antes/después de cada tool call)
- Session recording (guardar cada evento)
- Streaming display (Rich live output)
- Permission checks (¿ejecutar o preguntar?)

### Opción B: loop manual (NO para MVP)

Más control, mucho más código. Reservar para cuando el SDK se quede corto.

---

## 3. Cómo funcionan los tools

Cada tool es una función Python pura con type hints y docstring:

```python
def read_file(path: str) -> str:
    """
    Read the contents of a file at the given path.
    Returns the file content as a string.
    Use this to inspect source files before editing them.

    Args:
        path: relative or absolute path to the file
    """
    ...
```

El docstring es lo que el modelo lee para decidir cuándo usar el tool.
El LM Studio SDK convierte automáticamente la función en un tool JSON schema.

**Reglas de diseño para tools:**
1. Siempre retornan string (el modelo solo puede leer texto)
2. Nunca lanzan excepciones — retornan un mensaje de error descriptivo
3. Path siempre relativo al working directory del agente
4. Timeout en todo lo que puede colgarse (shell, búsquedas)
5. Dry-run mode: si `permission_mode = "ask"`, mostrar qué va a hacer antes de hacerlo

---

## 4. Consideraciones de modelos locales

Los modelos locales tienen diferencias importantes con los cloud:

| Aspecto | Cloud (Claude, GPT-4) | Local (Qwen, DeepSeek) |
|---|---|---|
| Tool calling | muy fiable | varía mucho por modelo |
| Context window | 200k tokens | 8k-128k según modelo |
| Velocidad | rápido | más lento, depende del hardware |
| JSON output | muy consistente | a veces malformado |
| Siguiendo instrucciones | muy bueno | requiere prompt cuidadoso |

**Modelos recomendados para lmcode (en orden):**
1. `qwen2.5-coder-32b` — el mejor para coding tasks con tools
2. `deepseek-r1` — bueno para razonamiento, algo más lento
3. `qwen2.5-coder-7b` — para hardware limitado
4. Cualquier modelo con `tool_call` support en LM Studio

**Cómo el diseño acomoda estas diferencias:**

```python
# Retry con backoff si el tool call viene malformado
# (el SDK ya maneja esto, pero podemos añadir fallback)

# Prompt engineering defensivo:
SYSTEM_PROMPT = """
You are a coding assistant. When you need to interact with files or run
commands, use the provided tools. Always use tools instead of generating
code that describes what you would do.

IMPORTANT: Call one tool at a time. Wait for the result before calling
the next tool. Never invent tool results.
"""
```

**Detección de capability:**
```python
async def probe_tool_support(model) -> bool:
    """Test if the loaded model supports tool calling."""
    ...
```

---

## 5. Multi-agent y subagentes en paralelo

### La realidad del hardware local

LM Studio usa **una sola GPU** (o CPU). La inferencia es inherentemente secuencial.
Esto significa que "agentes en paralelo" en local = requests en cola en LM Studio.

Pero hay dos tipos de paralelismo que SÍ se pueden aprovechar:

```
1. Paralelismo de tools (IO-bound) — SIEMPRE disponible
   El agente llama 3 tools → las 3 se ejecutan en paralelo con asyncio
   (leer 3 archivos, buscar en 3 paths, etc.)

2. Paralelismo de agentes (CPU/GPU-bound) — serializado en GPU
   2 agentes hacen requests → LM Studio los encola → los procesa uno a uno
   El UX puede sentirse paralelo aunque la inferencia sea secuencial
```

### Arquitectura: Orchestrator → Worker Agents

```
OrchestratorAgent
    │
    ├── task_plan = await self.plan(task)
    │
    ├── WorkerAgent("implementar función X")
    ├── WorkerAgent("escribir tests para X")    ← dispatched con asyncio.gather
    └── WorkerAgent("actualizar documentación")
         │
         └── cada uno tiene su propio:
               - lms.AsyncLLM instance
               - Chat history
               - Tool set (puede ser diferente por agente)
               - Session recorder separado
```

```python
# agent/orchestrator.py

class OrchestratorAgent:
    async def run(self, task: str) -> str:
        # 1. El orquestador planea y divide el trabajo
        subtasks = await self._plan(task)

        # 2. Lanza todos los subagentes concurrentemente
        workers = [WorkerAgent(subtask, self.config) for subtask in subtasks]
        results = await asyncio.gather(*[w.run() for w in workers])

        # 3. El orquestador sintetiza los resultados
        return await self._synthesize(results)

    async def _plan(self, task: str) -> list[str]:
        """Usa el LLM para dividir la tarea en subtareas independientes."""
        ...

    async def _synthesize(self, results: list[WorkerResult]) -> str:
        """Usa el LLM para combinar los resultados en una respuesta final."""
        ...
```

### Comunicación entre agentes

Los agentes NO comparten estado. Se comunican solo por valores de retorno:

```
Orchestrator → WorkerAgent: string con la tarea
WorkerAgent → Orchestrator: WorkerResult(output, files_changed, commands_run)
```

Sin estado compartido = sin race conditions = fácil de razonar.

### Qué pasa en GPU cuando lanzas varios agentes

```
t=0  Agent A request ──→ LM Studio queue
t=0  Agent B request ──→ LM Studio queue
t=0  Agent C request ──→ LM Studio queue

t=1  LM Studio procesa A (GPU)
t=2  A termina, Tool execution (async, paralelo con B en cola)
t=2  LM Studio procesa B (GPU)
t=3  B termina...
```

Es secuencial en GPU pero el overhead de espera lo oculta la ejecución de tools.
En la práctica, 2-3 agentes en paralelo en un buen modelo local (~20 tok/s) funciona bien.

### Para el MVP: NO implementar orquestador

El MVP no necesita multi-agent. Pero el diseño debe prepararlo:
- `Agent` debe ser una clase, no funciones sueltas
- Toda la configuración del agente va en el constructor
- No usar estado global — todo por instancia

Cuando llegue el momento, añadir `OrchestratorAgent` que crea instancias de `Agent`.

---

## 6. Plugin system — cómo funciona

```python
# plugins/hookspecs.py

class LMCodeSpec:
    @hookspec
    def on_tool_call(self, tool_name: str, args: dict) -> dict | None:
        """Fired before a tool executes. Return modified args or None."""

    @hookspec
    def on_tool_result(self, tool_name: str, result: str) -> str | None:
        """Fired after a tool executes. Return modified result or None."""

    @hookspec
    def on_session_start(self, session_id: str, working_dir: str) -> None:
        """Fired when a session begins."""

    @hookspec
    def on_session_end(self, session_id: str) -> None:
        """Fired when a session ends."""
```

Plugin de terceros instalado con pip:
```python
# lmcode_docker_plugin/plugin.py

class DockerPlugin:
    @hookimpl
    def on_session_start(self, session_id, working_dir):
        self.container = start_docker_sandbox(working_dir)

    @hookimpl
    def on_tool_call(self, tool_name, args):
        if tool_name == "run_shell":
            # redirigir comandos shell al contenedor Docker
            args["sandbox"] = self.container.id
        return args
```

---

## 7. MCP + OpenAPI — diseño

```python
# mcp/openapi.py

import fastmcp

async def load_openapi_as_tools(spec_url: str, name: str) -> list[Tool]:
    """
    Carga un spec OpenAPI y devuelve los endpoints como tools.
    Cada endpoint del spec se convierte en un tool callable por el agente.
    """
    server = fastmcp.FastMCP.from_openapi(spec_url, name=name)
    tools = await server.get_tools()
    return [adapt_mcp_tool(t) for t in tools]
```

Flujo completo:
```
lmcode mcp add --openapi https://api.stripe.com/openapi.json --name stripe

→ FastMCP parsea el spec
→ genera un MCP server en proceso con todos los endpoints como tools
→ el agent loop puede llamar "stripe_create_payment_intent(amount=100, currency='eur')"
→ FastMCP hace la HTTP request real a la API
→ el resultado vuelve al agente como string
```

---

## 8. Session recording — formato de eventos

```jsonl
{"type":"session_start","id":"sess_001","ts":1234567890,"cwd":"/home/user/myproject"}
{"type":"user_message","ts":1234567891,"content":"fix the failing tests"}
{"type":"model_response","ts":1234567892,"content":"I'll start by reading the test file...","streaming":true}
{"type":"tool_call","ts":1234567893,"tool":"read_file","args":{"path":"tests/test_api.py"}}
{"type":"tool_result","ts":1234567894,"tool":"read_file","result":"def test_create_user():\n..."}
{"type":"tool_call","ts":1234567895,"tool":"run_shell","args":{"cmd":"pytest tests/ -x"}}
{"type":"tool_result","ts":1234567896,"tool":"run_shell","result":"FAILED tests/test_api.py::test_create_user"}
{"type":"file_edit","ts":1234567897,"path":"src/api.py","diff":"--- a\n+++ b\n@@ -10 +10 @@\n-    return None\n+    return user"}
{"type":"session_end","ts":1234567898,"id":"sess_001","rounds":4}
```

Este formato es lo que alimenta el session viewer de Textual.
