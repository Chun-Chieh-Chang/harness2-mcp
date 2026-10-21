# Tool guidance
Call exactly ONE tool per turn, as a JSON object:
- list_dir {"path": "."}
- read_file {"path": "..."}
- write_file {"path": "...", "content": "<complete new file>"}
- run_shell {"cmd": "..."}   (runs in the project dir, 60s limit)
- finish {"summary": "..."}
Paths are relative to the project root. write_file replaces the whole file.
