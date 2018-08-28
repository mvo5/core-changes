#!/bin/bash

set -e

for snap in core core18 core16; do
    OUTPUT=~/public_html/${snap}-changes
    mkdir -p "$OUTPUT"

    BASE=$(readlink -f "$(dirname "$0")/..")
    PATH="$BASE/bin":$PATH

    # generate per-channel changes
    for ch in edge beta candidate stable; do
        ARCHIVE="$BASE"/archive-"$snap"-"$ch"
        mkdir -p "$ARCHIVE"

        # ensure we have an archive of snaps available for the changes
        # generation
        (cd "$ARCHIVE" && snap download "--$ch" $snap >/dev/null 2>&1)

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
done
