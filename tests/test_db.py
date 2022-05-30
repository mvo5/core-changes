#!/usr/bin/python

import datetime
import gzip
import os
import sqlite3
import shutil
import subprocess
import tempfile
import unittest


from corechanges import CoreChangesDB, tmpdir


def make_mock_changelog(name, version):
    changelog = """%(name)s (%(version)s) xenial; urgency=medium

  * some change

 -- Some Girl <some.girl@canonical.com>  Mon, 21 Mar 2022 22:16:54 -0500

%(name)s (0.0.1) xenial; urgency=medium

  * some other change

 -- some guy <some.guy@canonical.com>  Mon, 21 Mar 2022 22:16:54 -0500
""" % {
        "name": name,
        "version": version,
    }
    return changelog


class CoreChangesDBTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmpdir)
        self.addCleanup(shutil.rmtree, self.tmpdir)

    def make_test_core(self, name, revno, version, debs):
        fname = os.path.join(self.tmpdir, "%s_%s.snap" % (name, revno))
        snap_yaml = "name: %s\nversion: %s\n" % (name, version)
        dpkg_list = []
        for name, ver in debs:
            dpkg_list.append("ii %s %s all" % (name, ver))
        with tmpdir() as tmp:
            snapdir = os.path.join(tmp, "%s_%s" % (name, revno))
            # add meta/snap.yaml
            snap_yaml_path = os.path.join(snapdir, "meta/snap.yaml")
            os.makedirs(os.path.dirname(snap_yaml_path))
            with open(snap_yaml_path, "w") as fp:
                fp.write(snap_yaml)
            # add usr/share/snappy/dpkg.list
            dpkg_list_path = os.path.join(snapdir, "usr/share/snappy/dpkg.list")
            os.makedirs(os.path.dirname(dpkg_list_path))
            with open(dpkg_list_path, "w") as fp:
                fp.write("\n".join(dpkg_list))
            # add usr/share/doc/<pkgname>/changelog.gz
            for debname, debver in debs:
                changelog_path = os.path.join(
                    snapdir, "usr", "share", "doc", debname, "changelog.gz"
                )
                os.makedirs(os.path.dirname(changelog_path))
                with gzip.open(changelog_path, "w") as fp:
                    s = make_mock_changelog(debname, debver)
                    fp.write(s.encode("utf-8"))
            subprocess.check_call(
                ["mksquashfs", snapdir, fname], stdout=subprocess.DEVNULL
            )
        return fname

    def test_db_can_insert(self):
        db = CoreChangesDB("test.db")
        # mock snap
        debs = [("libc6", "1.0"), ("snapd", "2.52")]
        s1 = self.make_test_core("core", "2", "16-2.52", debs)
        db.add_core(s1)
        with sqlite3.connect(db._dbpath) as con:
            res = con.execute("SELECT core_revno, core_version FROM cores;").fetchall()
            self.assertEqual(res, [(2, "16-2.52")])
            res = con.execute("SELECT deb_name, deb_version FROM debs;").fetchall()
            self.assertEqual(res, [("libc6", "1.0"), ("snapd", "2.52")])

    def test_db_integration(self):
        db = CoreChangesDB("test.db")
        # mock snap
        debs = [("libc6", "1.0"), ("snapd", "2.52")]
        s1 = self.make_test_core("core", "1", "16-2.52", debs)
        db.add_core(s1)
        debs = [("libc6", "1.0"), ("snapd", "2.54")]
        s2 = self.make_test_core("core", "2", "16-2.54", debs)
        db.add_core(s2)
        debs = [("libc6", "1.2"), ("snapd", "2.56")]
        s3 = self.make_test_core("core", "3", "16-2.56", debs)
        db.add_core(s3)
        # two revs
        change = db.gen_change("core", "1", "3")
        self.assertEqual(change.old_version, "16-2.52")
        self.assertEqual(change.new_version, "16-2.56")
        self.assertEqual(
            change.pkg_changes, {"libc6": ("1.0", "1.2"), "snapd": ("2.52", "2.56")}
        )
        # just one rev
        change = db.gen_change("core", "2", "3")
        self.assertEqual(change.old_version, "16-2.54")
        self.assertEqual(change.new_version, "16-2.56")
        self.assertEqual(
            change.pkg_changes, {"libc6": ("1.0", "1.2"), "snapd": ("2.54", "2.56")}
        )
        self.assertEqual(len(change.changelogs), 2)
        self.assertEqual(
            change.changelogs["libc6"].split("\n")[0],
            "libc6 (1.2) xenial; urgency=medium",
        )
        self.assertTrue(
            change.changelogs["snapd"].split("\n")[0],
            "snapd (16-2.56) xenial; urgency=medium",
        )

    def test_db_add_core_release(self):
        db = CoreChangesDB("test.db")
        db.add_core_release("core", 1, "stable")
        with sqlite3.connect(db._dbpath) as con:
            res = con.execute("SELECT * FROM releases;").fetchall()
            self.assertEqual(len(res), 1)
            row = res[0]
            self.assertEqual(row[0], "core")
            self.assertEqual(row[1], 1)
            self.assertEqual(row[2], "stable")
            # check that it looks like a iso8601 date
            self.assertRegex(row[3], "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9][2}:[0-9]{2}")
            d = datetime.datetime.fromisoformat(row[3])
            self.assertIsInstance(d, datetime.datetime)
        # add the same revision again, this won't be added
        db.add_core_release("core", 1, "stable")
        with sqlite3.connect(db._dbpath) as con:
            res = con.execute("SELECT * FROM releases;").fetchall()
            self.assertEqual(len(res), 1)
        # add the same revision for a different core snap, it's added
        db.add_core_release("core18", 1, "stable")
        with sqlite3.connect(db._dbpath) as con:
            res = con.execute("SELECT * FROM releases;").fetchall()
            self.assertEqual(len(res), 2)
            row = res[1]
            self.assertEqual(row[0], "core18")
            self.assertEqual(row[1], 1)
        # add a new revision for core
        db.add_core_release("core", 2, "stable")
        with sqlite3.connect(db._dbpath) as con:
            res = con.execute("SELECT * FROM releases;").fetchall()
            self.assertEqual(len(res), 3)
            row = res[2]
            self.assertEqual(row[0], "core")
            self.assertEqual(row[1], 2)

    def test_db_big(self):
        db = CoreChangesDB("test.db")
        for i in range(100):
            debs = [("libc6", "1.0"), ("snapd", "2.52")]
            s1 = self.make_test_core("core", i, "16-2.52", debs)
            db.add_core(s1)


if __name__ == "__main__":
    unittest.main()
