# Design Document (internal)

Architecture decisions, agent design, and multi-agent patterns for lmcode.

---

## 1. MVP — what to build first and in what order

### What is in scope for MVP

One single criterion: does `lmcode chat` work in a real repo and do something useful?

**In scope:**
- LM Studio connection (official Python SDK)
- Agent loop with tool calling
- 4 tools: `read_file`, `write_file`, `run_shell`, `search_code`
- Real-time streaming output
- Session recording (JSONL)
- `lmcode chat` and `lmcode run "<task>"`
- `LMCODE.md` read and injected into the system prompt

**Out of scope for MVP:**
- MCP / OpenAPI (v0.2)
- Plugin system (v0.2)
- Session viewer TUI (v0.3)
- Git tools (v0.2)
- Embeddings / semantic search (v0.4)
- Sub-agents (v1.0)

### Build order

```
Day 1
  1. pyproject.toml + uv sync + directory structure    (~30 min)
  2. config/settings.py + config/paths.py              (~30 min)
  3. tools/base.py + tools/registry.py                 (~45 min)
  4. tools/filesystem.py + tools/shell.py + tools/search (~1.5h)

Day 2
  5. agent/memory.py — read LMCODE.md                  (~30 min)
  6. agent/context.py — build the system prompt        (~45 min)
  7. agent/core.py — the agent loop                    (~2h)

Day 3
  8. session/models.py + session/recorder.py           (~1h)
  9. cli/app.py + cli/chat.py                          (~1.5h)
 10. basic tests + CI                                  (~1h)
```

By the end of Day 3: `lmcode chat` works end-to-end.

---

## 2. The agent loop — core design

### Option A: use `model.act()` from the SDK (recommended for MVP)

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

The SDK already implements the full loop:
```
prompt → LLM → tool call? → execute → append result → repeat → done
```

We only add on top:
- Plugin hooks (before/after each tool call)
- Session recording (save each event)
- Streaming display (Rich live output)
- Permission checks (execute or ask first?)

### Option B: manual loop (NOT for MVP)

More control, much more code. Reserve for when the SDK falls short.

---

## 3. How tools work

Each tool is a plain Python function with type hints and a docstring:

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

The docstring is what the model reads to decide when to use the tool.
The LM Studio SDK automatically converts the function into a JSON schema tool definition.

**Tool design rules:**
1. Always return a string (the model can only read text)
2. Never raise exceptions — return a descriptive error message instead
3. Paths are always relative to the agent's working directory
4. Add timeouts to anything that can hang (shell, searches)
5. Dry-run mode: if `permission_mode = "ask"`, show what it will do before doing it

---

## 4. Local model considerations

Local models differ from cloud models in important ways:

| Aspect | Cloud (Claude, GPT-4) | Local (Qwen, DeepSeek) |
|---|---|---|
| Tool calling | very reliable | varies a lot by model |
| Context window | 200k tokens | 8k–128k depending on model |
| Speed | fast | slower, depends on hardware |
| JSON output | very consistent | sometimes malformed |
| Instruction following | excellent | requires careful prompting |

**Recommended models for lmcode (in order):**
1. `qwen2.5-coder-32b` — best for coding tasks with tools
2. `deepseek-r1` — good at reasoning, somewhat slower
3. `qwen2.5-coder-7b` — for limited hardware
4. Any model with `tool_call` support in LM Studio

**How the design accommodates these differences:**

```python
# Retry with backoff if the tool call comes back malformed
# (the SDK already handles this, but we can add a fallback)

# Defensive system prompt:
SYSTEM_PROMPT = """
You are a coding assistant. When you need to interact with files or run
commands, use the provided tools. Always use tools instead of generating
code that describes what you would do.

IMPORTANT: Call one tool at a time. Wait for the result before calling
the next tool. Never invent tool results.
"""
```

**Capability detection:**
```python
async def probe_tool_support(model) -> bool:
    """Test if the loaded model supports tool calling."""
    ...
```

---

## 5. Multi-agent and parallel sub-agents

### The reality of local hardware

LM Studio uses **a single GPU** (or CPU). Inference is inherently sequential.
This means "parallel agents" on local hardware = requests queued in LM Studio.

But there are two types of parallelism that CAN be exploited:

```
1. Tool parallelism (IO-bound) — ALWAYS available
   Agent calls 3 tools → all 3 run in parallel via asyncio
   (read 3 files, search 3 paths, etc.)

2. Agent parallelism (CPU/GPU-bound) — serialized at GPU
   2 agents make requests → LM Studio queues them → processes one at a time
   The UX can feel parallel even though inference is sequential
```

### Architecture: Orchestrator → Worker Agents

```
OrchestratorAgent
    │
    ├── task_plan = await self.plan(task)
    │
    ├── WorkerAgent("implement function X")
    ├── WorkerAgent("write tests for X")    ← dispatched with asyncio.gather
    └── WorkerAgent("update documentation")
         │
         └── each has its own:
               - lms.AsyncLLM instance
               - Chat history
               - Tool set (can differ per agent)
               - Separate session recorder
```

```python
# agent/orchestrator.py

class OrchestratorAgent:
    async def run(self, task: str) -> str:
        # 1. Orchestrator plans and breaks down the work
        subtasks = await self._plan(task)

        # 2. Launch all sub-agents concurrently
        workers = [WorkerAgent(subtask, self.config) for subtask in subtasks]
        results = await asyncio.gather(*[w.run() for w in workers])

        # 3. Orchestrator synthesizes the results
        return await self._synthesize(results)

    async def _plan(self, task: str) -> list[str]:
        """Use the LLM to break the task into independent sub-tasks."""
        ...

    async def _synthesize(self, results: list[WorkerResult]) -> str:
        """Use the LLM to combine results into a final response."""
        ...
```

### Agent communication

Agents do NOT share state. They communicate only through return values:

```
Orchestrator → WorkerAgent: string with the task
WorkerAgent → Orchestrator: WorkerResult(output, files_changed, commands_run)
```

No shared state = no race conditions = easy to reason about.

### What happens at the GPU when you launch multiple agents

```
t=0  Agent A request ──→ LM Studio queue
t=0  Agent B request ──→ LM Studio queue
t=0  Agent C request ──→ LM Studio queue

t=1  LM Studio processes A (GPU)
t=2  A finishes, tool execution (async, runs while B is queued)
t=2  LM Studio processes B (GPU)
t=3  B finishes...
```

Sequential at the GPU, but the waiting overhead is hidden by tool execution.
In practice, 2–3 parallel agents on a good local model (~20 tok/s) works well.

### For MVP: do NOT implement the orchestrator

The MVP does not need multi-agent. But the design must prepare for it:
- `Agent` must be a class, not loose functions
- All agent configuration goes in the constructor
- No global state — everything per instance

When the time comes, add `OrchestratorAgent` that creates `Agent` instances.

---

## 6. Plugin system — how it works

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

Third-party plugin installed via pip:
```python
# lmcode_docker_plugin/plugin.py

class DockerPlugin:
    @hookimpl
    def on_session_start(self, session_id, working_dir):
        self.container = start_docker_sandbox(working_dir)

    @hookimpl
    def on_tool_call(self, tool_name, args):
        if tool_name == "run_shell":
            # redirect shell commands into the Docker container
            args["sandbox"] = self.container.id
        return args
```

---

## 7. MCP + OpenAPI — design

```python
# mcp/openapi.py

import fastmcp

async def load_openapi_as_tools(spec_url: str, name: str) -> list[Tool]:
    """
    Load an OpenAPI spec and return the endpoints as agent tools.
    Each endpoint in the spec becomes a callable tool in the agent loop.
    """
    server = fastmcp.FastMCP.from_openapi(spec_url, name=name)
    tools = await server.get_tools()
    return [adapt_mcp_tool(t) for t in tools]
```

Full flow:
```
lmcode mcp add --openapi https://api.stripe.com/openapi.json --name stripe

→ FastMCP parses the spec
→ creates an in-process MCP server with all endpoints as tools
→ the agent loop can call "stripe_create_payment_intent(amount=100, currency='eur')"
→ FastMCP makes the real HTTP request to the API
→ the result comes back to the agent as a string
```

---

## 8. Session recording — event format

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

This format feeds the Textual session viewer.
