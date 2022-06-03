#!/bin/bash

set -e

LEGACY_DIR=~/core-changes

BASE=$(readlink -f "$(dirname "$0")/..")
PATH="$BASE/bin":$PATH


for snap in core22 core20 core core18 core16; do
    for ch in edge beta candidate stable; do
        ARCHIVE="$LEGACY_DIR"/archive-"$snap"-"$ch"

        gen-core-changes.py --import-to-db -v \
                            --archive-dir "$ARCHIVE" \
                            --track "$ch" \
                            --snap "$snap"
    done
done
