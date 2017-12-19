#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# no python3 on lillypilly (ubuntu 12.04)

import argparse
import datetime
import glob
import gzip
import os
import re
import shutil
import subprocess
import sys
import tempfile

import jinja2

try:
    from typing import Dict, List, Tuple
    Dict  # pyflakes
    List  # pyflakes
    Tuple  # pyflakes
except ImportError:
    pass


class tmpdir:
    """ tmpdir provides a temporary directory via a context manager"""
    def __enter__(self):
        # type: () -> str
        self.tmp = tempfile.mkdtemp()
        return self.tmp
    def __exit__(self, *args):
        shutil.rmtree(self.tmp)


class Change:
    """ Change contains the changes from old_version to new version """
    def __init__(self, old_version, new_version, date_new, diff, changelogs):
        # type: (str, str, datetime.datetime, Dict[str, Tuple[str, str]], Dict[str, str]) -> None
        self.old_version = old_version
        self.new_version = new_version
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
            ["unsquashfs", "-f", "-d", tmp, snap, data], stdout=devnull)
    

def core_version(snap):
    # type: (str) -> str
    """
    core_version returns the version number of snapd in the given core snap
    """
    version = "unknown"
    with tmpdir() as tmp:
        unsquashfs(tmp, snap, "/usr/lib/snapd/info")
        with open(os.path.join(tmp, "usr/lib/snapd/info")) as fp:
            for line in fp.readlines():
                line = line.strip()
                if line.startswith("VERSION="):
                    version = line.split("=")[1]
    return version


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
                l = re.split(r'\s+',line)
                name = l[1]
                ver = l[2]
                pkgs[name] = ver
    return pkgs


def debs_delta(debs_a, debs_b):
    # type: (Dict[str, str], Dict[str, str]) -> Dict[str, Tuple[str, str]]
    """debs_delta generates the delta between two deb package dicts"""
    diff = {}  # type: Dict[str, Tuple[str, str]]
    # in a but not in b
    for name in debs_a:
        if not name in debs_b:
            diff[name] = (debs_a[name], "")
    # in b but not in a
    for name in debs_b:
        if not name in debs_a:
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
            if "("+old_version+")" in line:
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
        unsquashfs(tmp, new_snap, "/usr/share/doc/*/changelog*")
        for name in pkg_changes:
            old_ver, new_ver = pkg_changes[name]
            for chglogname in ["changelog.Debian.gz", "changelog.gz"]:
                changelog_path = os.path.join(
                    tmp,"usr/share/doc",name, chglogname)
                if not os.path.exists(changelog_path) or os.path.islink(changelog_path):
                    continue
                if not name in changelogs:
                    changelogs[name] = ""
                changelogs[name] = changelog_until(changelog_path, old_ver)
                break
    return changelogs


def build_date(snap):
    # type: (str) -> datetime.datetime
    """build_date returns the build date of the given snap"""
    with tmpdir() as tmp:
        unsquashfs(tmp, snap, "/usr/lib/snapd/info")
        mtime = os.path.getmtime(os.path.join(tmp, "usr/lib/snapd/info"))
        return datetime.datetime.fromtimestamp(mtime)


def snap_change(old_snap, new_snap):
    # type: (str, str) -> Change
    """snap_change returns a Change object for the given two snaps"""
    old_ver = core_version(old_snap)
    new_ver= core_version(new_snap)
    diff = debs_delta(core_debs(old_snap), core_debs(new_snap))
    changelogs = deb_changelogs(new_snap, diff)
    bd = build_date(new_snap)
    return Change(old_ver, new_ver, bd, diff, changelogs)


def all_snap_changes(archive_dir):
    # type: (str) -> List[Change]
    """
    all_snap_changes generates a list of changes for all snaps in archive_dir
    """
    all_changes = []  # type: List[Change]
    snaps=sorted(
        glob.glob(archive_dir+"/*.snap"), key=lambda p: int(re.match(r'.*_([0-9]+).snap', p).group(1)))
    for i in range(len(snaps)-1):
        a = snaps[i]
        b = snaps[i+1]
        all_changes.append(snap_change(a,b))
    all_changes.reverse()
    return all_changes


def render_as_text(changes):
    # type: (List[Change]) -> None
    """render_as_text renders the given changes via text output"""
    for chg in changes:
        print("# Core snap %s to %s (build %s)" % (chg.old_version, chg.new_version, chg.build_date))
        print("\n")
        print("## Package changes\n")
        for deb, (old_ver, new_ver) in sorted(chg.pkg_changes.items()):
            print(" * %s: %s -> %s" % (deb, old_ver, new_ver))
        print("\n")
        print("## Changelogs\n")
        for name, changelog in chg.changelogs.items():
            print("%s" % changelog.encode("utf-8"))
            print("\n")


def gen_html_filename(chg):
    # type: (Change) -> str
    """
    gen_html_filename returns the filename of a change for the html renderer
    """
    return "%s_%s.html" % (chg.old_version, chg.new_version)


def render_as_html(changes, output_dir):
    """render_as_html renders the given changes as html"""
    os.makedirs(output_dir)
    loader=jinja2.FileSystemLoader(
        os.path.join(os.path.dirname(__file__), "..", "templates"))
    env = jinja2.Environment(loader=loader, autoescape=True)
    env.filters["gen_html_filename"] = gen_html_filename
    with open(os.path.join(output_dir, "index.html"), "wb") as index_fp:
        index = env.get_template('index.html')
        output = index.render(changes=changes)
        index_fp.write(output.encode("utf-8"))
    for chg in changes:
        details_html = os.path.join(output_dir, gen_html_filename(chg))
        with open(details_html, "wb") as details_fp:
            details = env.get_template('change_details.html')
            output = details.render(change=chg)
            details_fp.write(output.encode("utf-8"))

   
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('archive_dir')
    parser.add_argument('--markdown', action='store_true')
    parser.add_argument('--html', action='store_true')
    parser.add_argument('--output-dir', default="./html")
    args = parser.parse_args()
    
    all_changes = all_snap_changes(args.archive_dir)
    if args.markdown:
        render_as_text(all_changes)
    elif args.html:
        render_as_html(all_changes, args.output_dir)
    else:
        print("no output format selected, use --html or --markdown")
        sys.exit(1)
