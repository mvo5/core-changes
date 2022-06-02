#!/bin/bash

set -e

BASE=$(readlink -f "$(dirname "$0")/..")
ARCHIVE="$BASE"/cache

for snap in core22 core20 core18 core; do
    OUTPUT=~/public_html/changes/"${snap}"
    mkdir -p "$OUTPUT"

    PATH="$BASE/bin":$PATH

    # generate per-channel changes
    for ch in edge beta candidate stable; do
        mkdir -p "$ARCHIVE"

        # download the current $snap/$ch (exiting snaps won't get re-downloaded)
        filename=$(snap download --target-directory="$ARCHIVE" --"$ch" "$snap" | grep "snap install " | awk '{print $3}')
	# add to DB (adding is idempotent)
 	gen-core-changes.py --add-snap-to-db --snap="$filename" --track="$ch"

        # generate the html changes from the db
        CHANGES="$OUTPUT/$ch"
        gen-core-changes.py --html --output-dir "${CHANGES}".new --snap="$snap" --track="$ch"

        # move things in place
        if [ -d ${CHANGES} ]; then
            mv ${CHANGES} ${CHANGES}.old
        fi
        mv ${CHANGES}.new ${CHANGES}
        rm -rf ${CHANGES}.old
    done
done

# XXX: clean cached items older than 30days
echo "would delete"
find "$ARCHIVE" -mtime +30 -print
#find "$ARCHIVE" -mtime +30 -print0 | xargs -0 rm -f
