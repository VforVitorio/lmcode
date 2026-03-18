# Session Recording

> Session recording is planned for a future release. This document describes the intended design.

Every agent run will be recorded as a JSONL file in `~/.local/share/lmcode/sessions/` (or the platform equivalent via platformdirs).

## File format

Each line is a JSON object with a `type` discriminator field:

```jsonl
{"type": "session_start", "session_id": "abc123", "timestamp": "2026-01-01T12:00:00Z", "model": "llama-3.2", "cwd": "/home/user/project"}
{"type": "user_message", "session_id": "abc123", "timestamp": "...", "content": "fix the bug in main.py"}
{"type": "tool_call", "session_id": "abc123", "timestamp": "...", "tool": "read_file", "args": {"path": "main.py"}}
{"type": "tool_result", "session_id": "abc123", "timestamp": "...", "tool": "read_file", "output": "...file contents..."}
{"type": "model_response", "session_id": "abc123", "timestamp": "...", "content": "I found the issue..."}
{"type": "file_edit", "session_id": "abc123", "timestamp": "...", "path": "main.py", "diff": "...unified diff..."}
{"type": "session_end", "session_id": "abc123", "timestamp": "...", "rounds": 3, "exit_reason": "task_complete"}
```

## Event types

Defined in `src/lmcode/session/models.py` as a Pydantic union:

```python
SessionEvent = (
    SessionStartEvent
    | SessionEndEvent
    | UserMessageEvent
    | ModelResponseEvent
    | ToolCallEvent
    | ToolResultEvent
    | FileEditEvent
)
```

| Event | Fields |
|-------|--------|
| `session_start` | `session_id`, `timestamp`, `model`, `cwd` |
| `session_end` | `session_id`, `timestamp`, `rounds`, `exit_reason` |
| `user_message` | `session_id`, `timestamp`, `content` |
| `model_response` | `session_id`, `timestamp`, `content` |
| `tool_call` | `session_id`, `timestamp`, `tool`, `args` |
| `tool_result` | `session_id`, `timestamp`, `tool`, `output`, `error` |
| `file_edit` | `session_id`, `timestamp`, `path`, `diff` |

## Session viewer

`lmcode session view <id>` will open a [Textual](https://textual.textualize.io/) TUI with:

- Timeline of events on the left
- Full message/diff content on the right
- Keyboard navigation through tool calls and edits
