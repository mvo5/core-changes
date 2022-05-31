#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# no python3 on lillypilly (ubuntu 12.04)

import argparse
import datetime
import glob
import gzip
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile

import apt
import jinja2
import sqlite3

try:
    from typing import Dict, List, Tuple

    Dict  # pyflakes
    List  # pyflakes
    Tuple  # pyflakes
except ImportError:
    pass


class CoreChangesDB:
    def __init__(self, dbpath):
        self._dbpath = dbpath
        with sqlite3.connect(self._dbpath) as con:
            # XXX: add indexes
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS "cores"
                (
                  [core_name] TEXT NOT NULL,
                  [core_revno] INTEGER NOT NULL,
                  [core_version] TEXT,
                  [core_build_date] TEXT,
                  PRIMARY KEY (core_name, core_revno)
                );
                CREATE TABLE IF NOT EXISTS "debs"
                (
                  [deb_name] TEXT NOT NULL,
                  [deb_version] TEXT NOT NULL,
                  [changelog] TEXT,
                  PRIMARY KEY (deb_name, deb_version)
                );
                CREATE TABLE IF NOT EXISTS "coresdebs"
                (
                  [core_name] TEXT NOT NULL,
                  [core_revno] INTEGER NOT NULL,
                  [deb_name] TEXT NOT NULL,
                  [deb_version] TEXT NOT NULL,
                  PRIMARY KEY (core_name, core_revno, deb_name, deb_version)
                );
                CREATE TABLE IF NOT EXISTS "releases"
                (
                  [core_name] TEXT NOT NULL,
                  [core_revno] INTEGER NOT NULL,
                  [track] TEXT NOT NULL,
                  [date] TEXT NOT NULL
                );
            """
            )

    def add_core_release(self, core_name, revno, track):
        with sqlite3.connect(self._dbpath) as con:
            # XXX: do this in one sql statement?
            cur = con.execute(
                """
                SELECT core_name,core_revno,track FROM "releases"
                WHERE core_name = ? and track = ?
                ORDER BY rowid DESC LIMIT 1;
                """,
                (core_name, track),
            )
            row = cur.fetchone()
            if (
                row is not None
                and row[0] == core_name
                and row[1] == revno
                and row[2] == track
            ):
                return
            # new revision, add
            now = datetime.datetime.utcnow()
            con.execute(
                """
                INSERT INTO "releases" (core_name, core_revno, track, date)
                VALUES (?, ?, ?, ?)
                """,
                (core_name, revno, track, now.isoformat()),
            )

    def add_core(self, snap, track=""):
        core_name, revno = core_name_revno(snap)
        ver = core_version(snap)
        bd = build_date(snap)
        debs = core_debs(snap)
        changelogs = deb_changelogs_all(snap)
        with sqlite3.connect(self._dbpath) as con:
            # add snap
            con.execute(
                """
            INSERT OR IGNORE INTO "cores" (core_name, core_revno, core_version, core_build_date)
            VALUES (?, ?, ?, ?)
            """,
                (core_name, revno, ver, bd),
            )
            # add debs
            for deb_name, deb_ver in debs.items():
                deb_changelog = changelogs.get(deb_name)
                con.execute(
                    """
                INSERT OR IGNORE INTO "debs" (deb_name, deb_version, changelog)
                VALUES (?, ?, ?)
                """,
                    (deb_name, deb_ver, deb_changelog),
                )
                # add relation
                con.execute(
                    """
                INSERT OR IGNORE INTO "coresdebs" (core_name, core_revno, deb_name, deb_version)
                VALUES (?, ?, ?, ?)
                """,
                    (core_name, revno, deb_name, deb_ver),
                )
        if track != "":
            self.add_core_release(core_name, revno, track)

    def get_changes_for(self, core_name, track):
        changes = []
        with sqlite3.connect(self._dbpath) as con:
            cur = con.execute(
                """
                SELECT core_revno FROM releases
                WHERE core_name = ? and track = ?
                """,
                (core_name, track),
            )
            old_revno = None
            for row in cur.fetchall():
                revno = row[0]
                if old_revno is not None:
                    change = self._gen_change(core_name, old_revno, revno)
                    changes.insert(0, change)
                old_revno = revno
        return changes

    def _gen_change(self, core_name, old_revno, new_revno):
        changelogs = {}
        pkg_diff = {}
        with sqlite3.connect(self._dbpath) as con:
            cur = con.execute(
                """
            SELECT new.deb_name, new.deb_version, old.deb_version, debs.changelog, cores.core_build_date, cores.core_version, old_cores.core_version
            FROM coresdebs AS old, debs, cores, cores AS old_cores
            JOIN coresdebs AS new ON old.deb_name = new.deb_name and new.deb_version != old.deb_version
            WHERE old.core_name=? and new.core_name=? and old.core_revno=? and new.core_revno=? and debs.deb_name == new.deb_name and debs.deb_version == new.deb_version and new.core_revno = cores.core_revno and old.core_revno = old_cores.core_revno
            """,
                (core_name, core_name, old_revno, new_revno),
            )
            for row in cur.fetchall():
                deb_name, new_debver, old_debver, = (
                    row[0],
                    row[1],
                    row[2],
                )
                new_cl = row[3]
                bd = row[4]
                new_ver = row[5]
                old_ver = row[6]
                pkg_diff[deb_name] = (old_debver, new_debver)
                changelog = []
                if new_cl:
                    for line in new_cl.split("\n"):
                        m = re.match(r"[a-z0-9]+ \((.*)\) [a-z-]+; urgency=.*", line)
                        if m:
                            if apt.apt_pkg.version_compare(m.group(1), old_debver) < 0:
                                break
                        changelog.append(line)
                changelogs[deb_name] = "\n".join(changelog)
        return Change(old_ver, old_revno, new_ver, new_revno, bd, pkg_diff, changelogs)


def deb_changelogs_all(new_snap):
    # type: (str) -> Dict[str, str]
    changelogs = {}  # type: Dict[str, str]
    debs = core_debs(new_snap)
    with tmpdir() as tmp:
        unsquashfs(tmp, new_snap, "/usr/share/doc/*")
        for debname in debs:
            # split of multi-arch tag
            fsname = debname.split(":")[0]
            for chglogname in ["changelog.Debian.gz", "changelog.gz"]:
                changelog_path = os.path.join(tmp, "usr/share/doc", fsname, chglogname)
                if not os.path.exists(changelog_path):
                    continue
                if debname not in changelogs:
                    changelogs[debname] = ""
                with gzip.open(changelog_path) as changelog:
                    changelog_byte = changelog.read()
                    changelogs[debname] = changelog_byte.decode(
                        "utf-8", errors="xmlcharrefreplace"
                    )
                break
    return changelogs


class tmpdir:
    """tmpdir provides a temporary directory via a context manager"""

    def __enter__(self):
        # type: () -> str
        self.tmp = tempfile.mkdtemp()
        return self.tmp

    def __exit__(self, *args):
        shutil.rmtree(self.tmp)


class Change:
    """Change contains the changes from old_version to new version"""

    def __init__(
        self, old_version, old_revno, new_version, new_revno, date_new, diff, changelogs
    ):
        # type: (str, str, str, str, datetime.datetime, Dict[str, Tuple[str, str]], Dict[str, str]) -> None
        self.old_version = old_version
        self.old_revno = old_revno
        self.new_version = new_version
        self.new_revno = new_revno
        self.build_date = date_new
        self.pkg_changes = diff
        self.changelogs = changelogs

    def __repr__(self):
        return "<Change old=%s new=%s>" % (self.old_version, self.new_version)


def unsquashfs(tmp, snap, data=""):
    # type: (str, str, str) -> None
    """unsquashfs unsquashes the given snap into the given tmpdir

    The optional "data" argument can be used to extract only specific
    files or directories from the squashfs. It may contain wildcards.
    """
    with open(os.devnull, "w") as devnull:
        subprocess.check_call(
            ["unsquashfs", "-f", "-d", tmp, snap, data], stdout=devnull
        )


def core_version(snap):
    # type: (str) -> str
    """
    core_version returns the version number of snapd in the given core snap
    """
    version = ""
    with tmpdir() as tmp:
        unsquashfs(tmp, snap, "/usr/lib/snapd/info")
        infop = os.path.join(tmp, "usr/lib/snapd/info")
        if not os.path.exists(infop):
            # try meta/snap.yaml
            unsquashfs(tmp, snap, "/meta/snap.yaml")
            infop = os.path.join(tmp, "meta/snap.yaml")
        with open(infop) as fp:
            for line in fp.readlines():
                line = line.strip()
                if line.startswith("VERSION="):
                    version = line.split("=")[1]
                    return version
                if line.startswith("version:"):
                    version = line.split(":")[1]
                    return version.strip()
    return "unknown"


def core_name_revno(snap):
    # type: (str) -> Tuple[str, str]
    snap = os.path.basename(snap)
    m = re.match(r"([a-zA-Z0-9]+)_([0-9]+)\.snap", snap)
    if not m:
        raise Exception("cannot extract revno from '%s'" % snap)
    return m.group(1), m.group(2)


def core_debs(snap):
    # type: (str) -> Dict[str, str]
    """core_debs returns a map of deb names/versions in the given core snap"""
    pkgs = {}  # type: Dict[str, str]
    with tmpdir() as tmp:
        unsquashfs(tmp, snap, "/usr/share/snappy/dpkg.list")
        with open(os.path.join(tmp, "usr/share/snappy/dpkg.list")) as fp:
            for line in fp.readlines():
                line = line.strip()
                if not line.startswith("ii"):
                    continue
                li = re.split(r"\s+", line)
                name = li[1]
                ver = li[2]
                pkgs[name] = ver
    return pkgs


def debs_delta(debs_a, debs_b):
    # type: (Dict[str, str], Dict[str, str]) -> Dict[str, Tuple[str, str]]
    """debs_delta generates the delta between two deb package dicts"""
    diff = {}  # type: Dict[str, Tuple[str, str]]
    # in a but not in b
    for name in debs_a:
        if name not in debs_b:
            diff[name] = (debs_a[name], "")
    # in b but not in a
    for name in debs_b:
        if name not in debs_a:
            diff[name] = ("", debs_b[name])
    # in both
    for name in debs_a:
        if name in debs_b and debs_a[name] != debs_b[name]:
            diff[name] = (debs_a[name], debs_b[name])
    return diff


def changelog_until(changelog_path, old_version):
    # type: (str, str) -> str
    """
    changelog_until reads the given changelog path until it find "old_version"
    """
    lines = []
    with gzip.open(changelog_path) as changelog:
        for raw in changelog:
            line = raw.decode("utf-8", errors="xmlcharrefreplace")
            line = line.rstrip()
            # FIXME: make this smater
            if "(" + old_version + ")" in line:
                break
            lines.append(line)
    return "\n".join(lines)


def deb_changelogs(new_snap, pkg_changes):
    # type: (str, Dict[str, Tuple[str, str]]) -> Dict[str, str]
    """
    deb_changelogs returns all changelogs from snap for the given pkg_changes
    """
    changelogs = {}  # type: Dict[str, str]
    with tmpdir() as tmp:
        unsquashfs(tmp, new_snap, "/usr/share/doc/*")
        for name in pkg_changes:
            old_ver, new_ver = pkg_changes[name]
            # split of multi-arch tag
            fsname = name.split(":")[0]
            for chglogname in ["changelog.Debian.gz", "changelog.gz"]:
                changelog_path = os.path.join(tmp, "usr/share/doc", fsname, chglogname)
                if not os.path.exists(changelog_path):
                    continue
                if name not in changelogs:
                    changelogs[name] = ""
                changelogs[name] = changelog_until(changelog_path, old_ver)
                break
    return changelogs


def build_date(snap):
    # type: (str) -> datetime.datetime
    """build_date returns the build date of the given snap"""
    with tmpdir() as tmp:
        unsquashfs(tmp, snap, "/usr/share/snappy/dpkg.list")
        mtime = os.path.getmtime(os.path.join(tmp, "usr/share/snappy/dpkg.list"))
        return datetime.datetime.fromtimestamp(mtime)


def snap_change(old_snap, new_snap):
    # type: (str, str) -> Change
    """snap_change returns a Change object for the given two snaps"""
    old_ver = core_version(old_snap)
    _, old_revno = core_name_revno(old_snap)
    new_ver = core_version(new_snap)
    _, new_revno = core_name_revno(new_snap)
    diff = debs_delta(core_debs(old_snap), core_debs(new_snap))
    changelogs = deb_changelogs(new_snap, diff)
    bd = build_date(new_snap)
    return Change(old_ver, old_revno, new_ver, new_revno, bd, diff, changelogs)


def sorted_snaps_in_dir(archive_dir):
    return sorted(
        glob.glob(archive_dir + "/*.snap"),
        key=lambda p: int(re.match(r".*_([0-9]+).snap", p).group(1)),
    )


def all_snap_changes(archive_dir):
    # type: (str) -> List[Change]
    """
    all_snap_changes generates a list of changes for all snaps in archive_dir
    """

    def _key(filename):
        # type: (str) -> int
        m = re.match(r".*_([0-9]+).snap", filename)
        if m is None:
            raise Exception("cannot extra revision from %s" % filename)
        return int(m.group(1))

    all_changes = []  # type: List[Change]
    snaps = sorted(glob.glob(archive_dir + "/*.snap"), key=_key)
    for i in range(len(snaps) - 1):
        a = snaps[i]
        b = snaps[i + 1]
        all_changes.append(snap_change(a, b))
    all_changes.reverse()
    return all_changes


def render_as_text(changes):
    # type: (List[Change]) -> None
    """render_as_text renders the given changes via text output"""
    for chg in changes:
        print(
            "# Core snap %s (r%s) to %s (r%s) (build %s)"
            % (
                chg.old_version,
                chg.old_revno,
                chg.new_version,
                chg.new_revno,
                chg.build_date,
            )
        )
        print("\n")
        print("## Package changes\n")
        for deb, (old_ver, new_ver) in sorted(chg.pkg_changes.items()):
            if old_ver == "":
                print(" * %s added" % deb)
            elif new_ver == "":
                print(" * %s removed" % deb)
            else:
                print(" * %s: %s -> %s" % (deb, old_ver, new_ver))
        print("\n")
        print("## Changelogs\n")
        for name, changelog in chg.changelogs.items():
            print("%r" % changelog.encode("utf-8"))
            print("\n")


def gen_html_filename(chg):
    # type: (Change) -> str
    """
    gen_html_filename returns the filename of a change for the html renderer
    """
    return "%sr%s_%sr%s.html" % (
        chg.old_version,
        chg.old_revno,
        chg.new_version,
        chg.new_revno,
    )


def render_as_html(changes, output_dir, channel):
    """render_as_html renders the given changes as html"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    loader = jinja2.FileSystemLoader(
        os.path.join(os.path.dirname(__file__), "..", "templates")
    )
    env = jinja2.Environment(loader=loader, autoescape=True)
    env.filters["gen_html_filename"] = gen_html_filename
    env.globals["now"] = datetime.datetime.utcnow().replace(microsecond=0)
    env.globals["channel"] = channel
    with open(os.path.join(output_dir, "index.html"), "wb") as index_fp:
        index = env.get_template("index.html")
        output = index.render(changes=changes)
        index_fp.write(output.encode("utf-8"))
    for chg in changes:
        details_html = os.path.join(output_dir, gen_html_filename(chg))
        with open(details_html, "wb") as details_fp:
            details = env.get_template("change_details.html")
            output = details.render(change=chg)
            details_fp.write(output.encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-dir")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--output-dir", default="./html")
    parser.add_argument("--track", required=True)
    parser.add_argument("--snap", required=True)
    parser.add_argument("--import-to-db", action="store_true")
    parser.add_argument("--gen-from-db", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    # XXX: rename to "mass-import-to-db" or something
    if args.import_to_db:
        imported = 0
        db = CoreChangesDB("known-cores.db")
        for snap in sorted_snaps_in_dir(args.archive_dir):
            db.add_core(snap, args.track)
            imported += 1
        logging.debug("imported %i snaps" % imported)
        sys.exit(0)

    # XXX: add import-one-snap to be compatible with the cron job

    # render db content
    db = CoreChangesDB("known-cores.db")
    all_changes = db.get_changes_for(args.snap, args.track)

    if args.markdown:
        render_as_text(all_changes)
    elif args.html:
        render_as_html(all_changes, args.output_dir, args.track)
    else:
        print("no output format selected, use --html or --markdown")
        sys.exit(1)
