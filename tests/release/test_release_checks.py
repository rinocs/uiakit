import unittest

from check_licenses import expression_allowed
from check_release import secret_free


class ReleaseChecksTest(unittest.TestCase):
    def test_secret_scanner_rejects_real_values_and_allows_placeholders(self):
        with self.assertRaises(SystemExit):
            secret_free('fixture', b'INTERNAL_API_KEY=super-secret-value\n')
        secret_free('fixture', b'INTERNAL_API_KEY=\n')
        secret_free('fixture', b'ISOLATED_PLUGIN_TOKEN=<segreto>\n')

    def test_license_expression_allowlist(self):
        self.assertTrue(expression_allowed('MIT'))
        self.assertTrue(expression_allowed('MIT OR Apache-2.0'))
        self.assertFalse(expression_allowed('NOASSERTION'))
        self.assertTrue(expression_allowed('GPL-3.0-only'))
        self.assertFalse(expression_allowed('LicenseRef-Proprietary'))


if __name__ == '__main__':
    unittest.main()
