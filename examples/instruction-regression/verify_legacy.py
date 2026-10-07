"""Independent normalization contract. Exit 2 indicates setup failure."""
import importlib.util
from pathlib import Path
import sys
try:
    spec = importlib.util.spec_from_file_location('labels', Path.cwd() / 'compatibility.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except Exception as error:
    print('Setup error:', error)
    sys.exit(2)
try:
    cases = [('  Hello  ', '  hello  '), ('ABC', 'abc'), ('\tMixed Case\n', '\tmixed case\n'), ('   ', '   ')]
    for value, expected in cases:
        actual = module.normalize_label(value)
        assert actual == expected, f'{value!r}: expected {expected!r}, got {actual!r}'
except (AssertionError, NotImplementedError) as error:
    print('Behavior failure:', error)
    sys.exit(1)
except Exception as error:
    print('Unexpected verifier/runtime error:', error)
    sys.exit(2)
print('PASS: all normalization contract cases')
