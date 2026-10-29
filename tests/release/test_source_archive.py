import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import release
from check_release import scan_archive, check_artifacts


class SourceArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.output = Path(self.temp.name) / 'output'
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Release fixture')
        (self.root / 'VERSION').write_text('0.1.0\n')
        (self.root / 'README.md').write_text('reviewed source\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'reviewed fixture')
        self.root_patch = patch.object(release, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root,
                                       stderr=subprocess.DEVNULL, text=True).strip()

    def test_only_commit_sources_enter_archive(self):
        for name in ('.env', '.bootstrap-admin-key', '.aws/credentials',
                     '.codex/state', '.worktrees/other/secret', 'data/blob',
                     'backups/backup.sql', 'untracked.txt'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic fixture only\n')
        archive = release.source_archive(self.output)
        with tarfile.open(archive) as source:
            members = {member.name.split('/', 1)[1] for member in source if member.isfile()}
        self.assertEqual(members, {'VERSION', 'README.md'})

    def test_dirty_tracked_sources_reject_before_creating_archive(self):
        for staged in (False, True):
            with self.subTest(staged=staged):
                (self.root / 'README.md').write_text('unreviewed changes\n')
                if staged:
                    self.git('add', 'README.md')
                with self.assertRaisesRegex(SystemExit, 'clean'):
                    release.source_archive(self.output)
                self.assertFalse(self.output.exists() and list(self.output.glob('*.gz')))

    def test_tracked_sensitive_paths_and_symlinks_fail_closed(self):
        for name in ('.aws/credentials', '.bootstrap-admin-key', '.env', 'external-link'):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if name == 'external-link':
                    path.symlink_to('/etc/hosts')
                else:
                    path.write_text('synthetic fixture only\n')
                self.git('add', name)
                self.git('commit', '-qm', 'unsafe fixture')
                with self.assertRaisesRegex(SystemExit, 'forbidden|symlink|unsupported'):
                    release.source_archive(self.output)
                self.git('rm', '-q', name)
                self.git('commit', '-qm', 'remove unsafe fixture')

    def test_missing_git_repository_has_no_filesystem_fallback(self):
        other = Path(self.temp.name) / 'not-git'
        other.mkdir()
        (other / 'VERSION').write_text('0.1.0\n')
        with patch.object(release, 'ROOT', other):
            with self.assertRaises(SystemExit):
                release.source_archive(self.output)

    def test_archives_check_sensitive_member_names_before_size_limit(self):
        self.output.mkdir()
        payload = b'x' * (5 * 1024 * 1024 + 1)
        for name in ('.aws/credentials', '.bootstrap-admin-key', '.env.production'):
            for kind in ('tar', 'zip'):
                with self.subTest(name=name, kind=kind):
                    archive = self.output / ('fixture.' + kind)
                    if kind == 'tar':
                        with tarfile.open(archive, 'w') as bundle:
                            info = tarfile.TarInfo('source/' + name)
                            info.size = len(payload)
                            bundle.addfile(info, io.BytesIO(payload))
                    else:
                        with zipfile.ZipFile(archive, 'w') as bundle:
                            bundle.writestr('source/' + name, payload)
                    with self.assertRaisesRegex(SystemExit, 'forbidden'):
                        scan_archive(archive.name, archive)

    def test_release_stages_reject_stale_output(self):
        self.output.mkdir()
        (self.output / 'old-package.tar.gz').write_bytes(b'stale')
        with self.assertRaisesRegex(SystemExit, 'stale|empty|unverified'):
            release.release_revision(self.output)

    def test_package_build_commands_use_exported_sources_not_working_directory(self):
        for name in ('packages/sdk-go/go.mod', 'packages/sdk-typescript/package.json',
                     'packages/sdk-php/composer.json'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'package fixture')
        (self.root / 'packages/sdk-typescript/untracked.txt').write_text('not reviewed')
        observed = []

        def run(command, *, cwd=None, env=None):
            directory = Path(cwd) if cwd else release.ROOT
            observed.append(command)
            self.assertFalse(directory.is_relative_to(self.root))
            self.assertFalse((directory / 'untracked.txt').exists())

        with patch.object(release, 'NPM_PACKAGES', ['packages/sdk-typescript']), \
                patch.object(release, 'PYTHON_PACKAGES', []), patch.object(release, 'run', run):
            release.prepare_packages(self.output)
        self.assertTrue(any(command[:2] == ['npm', 'ci'] for command in observed))
        self.assertTrue(any(command[:3] == ['npm', 'run', 'build'] for command in observed))

    def test_safe_env_template_and_release_tests_are_included(self):
        (self.root / '.env.example').write_text('MODEL_API_KEY=\n')
        tests = self.root / 'tests/release'
        tests.mkdir(parents=True)
        (tests / 'test_sample.py').write_text('pass\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'safe fixtures')
        archive = release.source_archive(self.output)
        with tarfile.open(archive) as source:
            names = source.getnames()
        self.assertIn('universal-ai-kit-0.1.0/.env.example', names)
        self.assertIn('universal-ai-kit-0.1.0/tests/release/test_sample.py', names)

    def candidate(self):
        contract = self.root / 'packages/api-contract/public.openapi.json'
        contract.parent.mkdir(parents=True)
        contract.write_text('{}\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'contract fixture')
        commit = release.release_revision(self.output)
        packages = self.output / 'packages'
        release.release_revision(packages)
        release.source_archive(packages)
        (self.output / 'sbom.cdx.json').write_text(json.dumps({'components': [
            {'name': 'fixture', 'licenses': [{'license': {'id': 'GPL-3.0-only'}}]}]}))
        (self.output / 'THIRD_PARTY_NOTICES.md').write_text('Fixture GPL-3.0-only\n')
        images = self.output / 'images'
        images.mkdir()
        image = images / 'fixture.tar'
        image.write_bytes(b'fixture image\n')
        (self.output / 'images.json').write_text(json.dumps([{
            'name': 'uai-fixture', 'tag': '0.1.0', 'image_id': 'sha256:fixture',
            'tar': image.name, 'tar_sha256': release.sha256(image),
            'labels': {'org.opencontainers.image.revision': commit,
                       'org.opencontainers.image.licenses': 'GPL-3.0-only'},
        }]))
        return commit

    def finalize(self):
        with patch.object(release, 'LOCKFILES', []):
            release.prepare_manifest(self.output)

    def test_downloaded_candidate_verifies_without_internal_markers(self):
        self.candidate()
        self.finalize()
        manifest = json.loads((self.output / 'manifest.json').read_text())
        self.assertFalse(any(Path(name).name == '.release-commit' for name in manifest['files']))
        self.assertNotIn('.release-commit', (self.output / 'SHA256SUMS').read_text())
        for marker in self.output.rglob('.release-commit'):
            marker.unlink()
        check_artifacts(self.output)

    def test_stale_or_missing_nested_stage_is_rejected(self):
        self.candidate()
        marker = self.output / 'packages/.release-commit'
        marker.write_text('0' * 40 + '\n')
        with self.assertRaisesRegex(SystemExit, 'commit|stage|stale'):
            self.finalize()
        marker.unlink()
        with self.assertRaisesRegex(SystemExit, 'commit|stage|missing'):
            self.finalize()

    def test_image_revision_must_match_candidate(self):
        self.candidate()
        path = self.output / 'images.json'
        images = json.loads(path.read_text())
        images[0]['labels']['org.opencontainers.image.revision'] = '0' * 40
        path.write_text(json.dumps(images))
        with self.assertRaisesRegex(SystemExit, 'revision|commit'):
            self.finalize()

    def test_downloaded_candidate_requires_commit_evidence(self):
        self.candidate()
        self.finalize()
        path = self.output / 'images.json'
        images = json.loads(path.read_text())
        del images[0]['labels']['org.opencontainers.image.revision']
        path.write_text(json.dumps(images))
        manifest_path = self.output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        del manifest['commit']
        manifest['files']['images.json'] = release.sha256(path)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(SystemExit, 'commit|revision'):
            check_artifacts(self.output)


if __name__ == '__main__':
    unittest.main()
