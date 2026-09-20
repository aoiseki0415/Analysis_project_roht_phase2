import os
import unittest

from utils.app_paths import application_root


class ApplicationRootTests(unittest.TestCase):
    def test_source_run_uses_project_root(self):
        expected = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(expected, application_root())
