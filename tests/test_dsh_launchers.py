import re
import unittest
from pathlib import Path


ROOT = Path('/home/alan/DSH-workspace/launchers')


class DshLaunchersTest(unittest.TestCase):
    def test_profiles_and_isolation_match(self):
        scripts = {
            'syncify': (ROOT / 'start-syncify-dsh.sh').read_text(),
            'rehabweb': (ROOT / 'start-rehabweb-dsh.sh').read_text(),
        }
        expected = {
            'syncify': ('workspaces/Syncify/dsh-home/.dsh', 'workspaces/Syncify/runtime/dsh-npm-cache', '3080'),
            'rehabweb': ('workspaces/RehabWeb/dsh-home/.dsh', 'workspaces/RehabWeb/runtime/dsh-npm-cache', '3081'),
        }
        for name, text in scripts.items():
            home, cache, port = expected[name]
            self.assertIn(f'DSH_HOME="$ROOT/{home}"', text)
            self.assertIn(f'CACHE="$ROOT/{cache}"', text)
            self.assertIn('PROFILE=${DSH_PROFILE:-web}', text)
            self.assertIn(f'node "$BIN" --profile "$PROFILE" --host 127.0.0.1 --port {port}', text)
            self.assertNotIn('node "$BIN" web ', text)
            self.assertRegex(text, r'BIN="\$ROOT/workspaces/Syncify/runtime/dsh-cli/node_modules/@deepseek-ai/dsh/lib/bin\.js"')


if __name__ == '__main__':
    unittest.main()
