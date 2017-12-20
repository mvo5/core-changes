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

    # generate the html changes
    CHANGES="$OUTPUT/html/$ch"
    gen-core-changes.py --html "$ARCHIVE" --channel "$ch" --output-dir "${CHANGES}".new

    # move things in place
    if [ -d ${CHANGES} ]; then
           mv ${CHANGES} ${CHANGES}.old
    fi
    mv ${CHANGES}.new ${CHANGES}
    rm -rf ${CHANGES}.old
done
