"""Credential loading treats dotenv input as data, never shell instructions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class EnvironmentLoaderTests(unittest.TestCase):
    def load(self, content, extra_env=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            loader = root / "scripts/load-jev-env.sh"
            shutil.copy2(Path(__file__).resolve().parents[1] / "scripts/load-jev-env.sh", loader)
            (root / ".env").write_text(content)
            clean = {k: v for k, v in os.environ.items() if k not in {
                "JEV_API_KEY", "TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "openouterkey",
            }}
            clean.update(extra_env or {})
            result = subprocess.run([
                "bash", "-c", 'set -e; source "$1"; exec "$2" -c "$3"',
                "loader-test", str(loader), sys.executable,
                'import json, os; print(json.dumps({k:os.getenv(k) for k in '
                '["TYPESAFE_API_KEY","OPENROUTER_API_KEY","TEST_LITERAL"]}))',
            ], env=clean, cwd=root, capture_output=True, text=True)
            return result, (root / "executed").exists()

    def test_legacy_keys_and_quoted_values_without_shell_execution(self):
        result, executed = self.load(
            'JEV_API_KEY = "fake jev"\nopenouterkey=fake-router # comment\n'
            'TEST_LITERAL=\'$(touch executed) `touch executed` $HOME\'\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual(values["TYPESAFE_API_KEY"], "fake jev")
        self.assertEqual(values["OPENROUTER_API_KEY"], "fake-router")
        self.assertEqual(values["TEST_LITERAL"], "$(touch executed) `touch executed` $HOME")
        self.assertFalse(executed)

    def test_official_key_takes_precedence_over_legacy_alias(self):
        result, _ = self.load('JEV_API_KEY=legacy\nTYPESAFE_API_KEY=official\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["TYPESAFE_API_KEY"], "official")

    def test_malformed_file_fails_even_with_existing_key(self):
        result, _ = self.load('JEV_API_KEY="unterminated\n', {"TYPESAFE_API_KEY": "existing"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
