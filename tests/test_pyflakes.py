#!/usr/bin/python

import os
import subprocess
import unittest


class PyflakesTestCase(unittest.TestCase):
    def test_pyflakes_clean(self):
        top_src_dir = os.path.join(os.path.dirname(__file__), "..", "bin")
        self.assertEqual(subprocess.call(["pyflakes3", top_src_dir]), 0)


if __name__ == "__main__":
    unittest.main()
