import json
import os
import subprocess
import sys
import unittest

from rulebisect.status import _powershell_argument, format_command


class PowerShellArgumentTests(unittest.TestCase):
    def test_smart_quotes_are_emitted_as_literal_characters(self):
        self.assertEqual(_powershell_argument("D’Arcy's"), "('D' + [char]8217 + 'Arcy''s')")

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell command parsing')
    def test_generated_command_roundtrips_through_powershell(self):
        path = "D’Arcy‘s ‚sample‛ $dir's copy"
        command = format_command([sys.executable, '-c', 'import json,sys; print(json.dumps(sys.argv[1:]))', path])
        result = subprocess.run(['pwsh', '-NoProfile', '-NonInteractive', '-Command', command],
                                check=True, capture_output=True, text=True, timeout=20)
        self.assertEqual(json.loads(result.stdout), [path])
