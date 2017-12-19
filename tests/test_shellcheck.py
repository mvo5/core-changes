#!/usr/bin/python

import glob
import os
import subprocess
import unittest


class ShellcheckTestCase(unittest.TestCase):

    def test_shellcheck_clean(self):
        top_src_dir = os.path.join(os.path.dirname(__file__), "..", "bin")
        self.assertEqual(subprocess.call(
            ["shellcheck"]+glob.glob(os.path.join(top_src_dir, "*.sh"))), 0)


if __name__ == "__main__":
    unittest.main()
