from pathlib import Path
import json
import sys
try:
    result = json.loads(Path("result.json").read_text())
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(1)
sys.exit(0 if result.get("format") == "modern" else 1)
