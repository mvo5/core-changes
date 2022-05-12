#!/usr/bin/python

import os
import subprocess
import unittest


def hasMyPy():
    try:
        subprocess.check_call(["mypy", "--version"])
    except Exception:
        return False
    return True


class PackagePep484TestCase(unittest.TestCase):
    @unittest.skipIf(not hasMyPy(), "no mypy available")
    def test_pep484_clean(self):
        top_src_dir = os.path.join(os.path.dirname(__file__), "..")
        dirs = [os.path.join(top_src_dir, "bin"), os.path.join(top_src_dir, "tests")]
        self.assertEqual(subprocess.call(["mypy"] + dirs), 0)


if __name__ == "__main__":
    unittest.main()
