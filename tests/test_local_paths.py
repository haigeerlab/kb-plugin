import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'check_local_paths.py'

# Real-looking account names are assembled at run time so this file never contains one.
NAME = 'al' + 'ice'
HOME = '/' + 'Users' + '/'
LINUX_HOME = '/' + 'home' + '/'
ENCODED = '-' + 'Users' + '-'


def load():
    spec = importlib.util.spec_from_file_location('check_local_paths', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HitsInTextTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_macos_linux_and_encoded_home_paths_are_hits(self):
        text = '\n'.join(['ok', HOME + NAME + '/Documents/kb', LINUX_HOME + NAME + '/work',
                          'session ' + ENCODED + NAME + '-Documents-kb'])
        self.assertEqual(self.mod.hits_in_text(text), [(2, 'path'), (3, 'path'), (4, 'encoded')])

    def test_placeholders_and_made_up_names_pass(self):
        text = '\n'.join(['~/Documents/kb', '$HOME/.config/kb', HOME + '<user>/kb', LINUX_HOME + '<user>/x',
                          HOME + 'example/kb', LINUX_HOME + 'runner/work', ENCODED + 'example-repo'])
        self.assertEqual(self.mod.hits_in_text(text), [])


class CliTests(unittest.TestCase):
    def repo(self, files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        subprocess.run(['git', 'add', '-A'], cwd=root, check=True)
        return root

    def run_cli(self, root):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--repo', str(root)],
                              capture_output=True, text=True)

    def test_hit_exits_1_and_never_echoes_the_line(self):
        secret_line = 'vault: ' + HOME + NAME + '/Documents/kb'
        root = self.repo({'docs/a.md': ('title\n' + secret_line + '\n').encode(), 'b.txt': b'clean\n'})
        result = self.run_cli(root)
        self.assertEqual(result.returncode, 1)
        self.assertIn('docs/a.md:2: path', result.stdout)
        self.assertNotIn(NAME, result.stdout + result.stderr)

    def test_clean_repo_exits_0(self):
        result = self.run_cli(self.repo({'a.md': b'~/Documents/kb\n'}))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_binary_and_untracked_files_are_skipped(self):
        root = self.repo({'bin.dat': b'\0' + (HOME + NAME + '/x').encode()})
        (root / 'untracked.md').write_text(HOME + NAME + '/x\n')
        self.assertEqual(self.run_cli(root).returncode, 0)

    def test_this_repository_is_clean(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
