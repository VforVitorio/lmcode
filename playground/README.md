# playground/

Safe sandbox for testing lmcode features end-to-end. Edit, delete, or break anything here — nothing affects the real codebase.

## Files

| File | Purpose |
|------|---------|
| `calculator.py` | Read/edit/run — good for testing `write_file` diff blocks |
| `data.json` | Read/edit JSON — good for structured edits |
| `notes.txt` | Plain text read/write |
| `script.sh` | Triggers `run_shell` IN/OUT panel |

## Test prompts to try

```
# read_file panel
lee el fichero playground/calculator.py

# write_file diff block (modification)
añade una función multiply(a, b) a playground/calculator.py

# write_file new file
crea un fichero playground/greet.py con una función que salude por nombre

# run_shell IN/OUT panel
ejecuta python playground/calculator.py

# multi-step flow
lee playground/data.json, añade un campo "version": "1.0" y guárdalo
```

## Recommended model for testing

**Qwen2.5-Coder-7B-Instruct Q4_K_M** (~4.5 GB VRAM)
- Best function calling for code tasks at 7B size
- Available in LM Studio model browser
- Works well with all lmcode tools
