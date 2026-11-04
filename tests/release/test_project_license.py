import json
from pathlib import Path
import sys
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import release
from check_release import PACKAGE_JSONS, PYPROJECTS
from check_licenses import expression_allowed


class ProjectLicenseTest(unittest.TestCase):
    def test_distributed_package_licenses_match_root(self):
        text = (ROOT / 'LICENSE').read_text()
        self.assertIn('GNU GENERAL PUBLIC LICENSE', text)
        self.assertIn('Version 3, 29 June 2007', text)
        directories = {str(Path(p).parent) for p in PYPROJECTS + PACKAGE_JSONS}
        directories.update(('packages/sdk-go', 'packages/sdk-php'))
        for directory in directories:
            with self.subTest(package=directory):
                self.assertEqual((ROOT / directory / 'LICENSE').read_text(), text)
        for manifest in PYPROJECTS:
            project = tomllib.loads((ROOT / manifest).read_text())['project']
            self.assertEqual(project['license'], 'GPL-3.0-only')
            self.assertIn('LICENSE', project['license-files'])
        for manifest in PACKAGE_JSONS + ['packages/sdk-php/composer.json']:
            self.assertEqual(json.loads((ROOT / manifest).read_text())['license'], 'GPL-3.0-only')
        for _, dockerfile in release.IMAGES:
            self.assertIn('org.opencontainers.image.licenses="GPL-3.0-only"',
                          (ROOT / dockerfile).read_text())

    def test_first_party_inventory_uses_gpl_without_relicensing_dependencies(self):
        with patch.multiple(release, python_components=lambda: {}, npm_components=lambda: {},
                            composer_components=lambda: {}, go_components=lambda: {}):
            components = release.all_components()
        self.assertEqual(len(components), len(release.FIRST_PARTY))
        for component in components:
            self.assertEqual(component['licenses'], [{'license': {'id': 'GPL-3.0-only'}}])
        self.assertTrue(expression_allowed('GPL-3.0-only'))
        self.assertFalse(expression_allowed('LicenseRef-Proprietary'))
        self.assertFalse(expression_allowed('NOASSERTION'))


if __name__ == '__main__':
    unittest.main()
