"""Optional integration check for maintainer launcher fixtures.

Set DSH_LAUNCHER_FIXTURE_ROOT to a directory containing the two historical
MVP launcher scripts. They are regression fixtures, not distributed defaults.
"""
import os
import re
import unittest
from pathlib import Path


class DshLaunchersTest(unittest.TestCase):
    def test_profiles_and_isolation_match(self):
        configured = os.environ.get('DSH_LAUNCHER_FIXTURE_ROOT')
        if not configured:
            self.skipTest('Set DSH_LAUNCHER_FIXTURE_ROOT for optional historical fixture integration')
        root = Path(configured)
        if not root.is_absolute() or root.resolve(strict=True) != root:
            self.fail('DSH_LAUNCHER_FIXTURE_ROOT must be an existing canonical absolute path')
        files = {
            'syncify': root / 'start-syncify-dsh.sh',
            'rehabweb': root / 'start-rehabweb-dsh.sh',
        }
        if not all(path.is_file() for path in files.values()):
            self.skipTest('Historical launcher fixtures are not available at the configured root')
        scripts = {name: path.read_text() for name, path in files.items()}
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
            self.assertRegex(
                text,
                r'BIN="\$ROOT/workspaces/Syncify/runtime/dsh-cli/node_modules/@deepseek-ai/dsh/lib/bin\.js"')


if __name__ == '__main__':
    unittest.main()
