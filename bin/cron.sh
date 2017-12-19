#!/bin/bash

set -e

OUTPUT=~/public_html/core-changes
mkdir -p "$OUTPUT"

BASE=$(readlink -f "$(dirname "$0")/..")
PATH="$BASE/bin":$PATH

# generate per-channel changes
for ch in stable candidate beta edge; do
    ARCHIVE="$BASE"/archive-"$ch"
    mkdir -p "$ARCHIVE"

    # ensure we have an archive of snaps available for the changes
    # generation
    (cd "$ARCHIVE" && snap download "--$ch" core >/dev/null 2>&1)

    # generate the changes
    CHANGES="$OUTPUT/changes-$ch.txt"
    gen-core-changes.py --markdown "$ARCHIVE" > "${CHANGES}".tmp

    echo "" >> "${CHANGES}".tmp
    echo "Generated on $(date)" >> "${CHANGES}".tmp

    # move things into place, don't change timestamp unless there are changes
    # so that if-modified-since etc works
    if [ ! -e $CHANGES ] || ! cmp <(grep -v "Generated on" "${CHANGES}".tmp) <(grep -v "Generated on" "$CHANGES") >/dev/null 2>&1; then
        mv "${CHANGES}.tmp" "$CHANGES"
    fi
    rm -f "${CHANGES}".tmp
done
