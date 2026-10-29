import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/bootstrap.py'


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        template = Path(__file__).resolve().parents[2] / '.env.example'
        (self.root / '.env.example').write_bytes(template.read_bytes())

    def bootstrap(self):
        spec = importlib.util.spec_from_file_location('bootstrap_fixture', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.bootstrap(self.root)

    def test_creates_private_complete_configuration_and_keeps_provider_fields(self):
        key = self.bootstrap()
        text = (self.root / '.env').read_text()
        values = dict(line.split('=', 1) for line in text.splitlines()
                      if line and not line.startswith('#'))
        self.assertEqual(values['UAI_API_KEY_SHA256'], hashlib.sha256(key.encode()).hexdigest())
        for name in ('POSTGRES_PASSWORD', 'INTERNAL_API_KEY', 'RUSTFS_ACCESS_KEY', 'RUSTFS_SECRET_KEY'):
            self.assertRegex(values[name], r'^[0-9a-f]{64}$')
        self.assertEqual(len({values[name] for name in ('POSTGRES_PASSWORD', 'INTERNAL_API_KEY',
                                                        'RUSTFS_ACCESS_KEY', 'RUSTFS_SECRET_KEY')}), 4)
        self.assertNotIn(key, text)
        self.assertEqual(values['MODEL_API_KEY'], '')
        self.assertEqual(stat.S_IMODE((self.root / '.env').stat().st_mode), 0o600)
        self.assertFalse((self.root / '.bootstrap-admin-key').exists())

    def test_rerun_and_existing_symlink_never_overwrite_configuration(self):
        key = self.bootstrap()
        before = (self.root / '.env').read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(SystemExit, 'exists'):
                self.bootstrap()
        self.assertEqual((self.root / '.env').read_bytes(), before)
        self.assertNotIn(key, output.getvalue())
        (self.root / '.env').unlink()
        outside = self.root / 'existing-secret'
        outside.write_text('do not replace')
        (self.root / '.env').symlink_to(outside)
        with self.assertRaises(SystemExit):
            self.bootstrap()
        self.assertEqual(outside.read_text(), 'do not replace')

    def test_missing_or_incomplete_template_leaves_no_env(self):
        for text in (None, 'POSTGRES_PASSWORD=\n'):
            with self.subTest(text=text):
                template = self.root / '.env.example'
                if text is None:
                    template.unlink()
                else:
                    template.write_text(text)
                with self.assertRaises(SystemExit):
                    self.bootstrap()
                self.assertFalse((self.root / '.env').exists())

    @unittest.skipUnless(__import__('shutil').which('docker'), 'Docker Compose unavailable')
    def test_generated_env_passes_clean_template_compose_interpolation(self):
        self.bootstrap()
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(['docker', 'compose', '--project-directory', str(root),
                                 '--env-file', str(self.root / '.env'), '-f', str(root / 'compose.yaml'),
                                 'config', '--quiet'], capture_output=True, text=True,
                                env={key: value for key, value in os.environ.items()
                                     if key in ('PATH', 'HOME', 'DOCKER_CONFIG')})
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
