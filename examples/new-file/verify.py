import importlib.util
from pathlib import Path
try:
    spec = importlib.util.spec_from_file_location("labels", Path.cwd()/"labels.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.normalize_label("  HELLO  ") == "hello"
    assert module.normalize_label("World") == "world"
except (AssertionError, FileNotFoundError, AttributeError):
    raise SystemExit(1)
