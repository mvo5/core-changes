#!/bin/bash

set -e

OUTPUT=~/public_html/core-changes
mkdir -p "$OUTPUT"

BASE=$(dirname "$0")/..
PATH=$PATH:"$BASE/bin"

# ensure we have an archive of cores
(cd "$BASE/archive" ; snap download --stable core 2>/dev/null)

# generate the changes
gen-core-changes.py "$BASE"/archive > "$OUTPUT"/changes.txt.tmp

echo "" >> "$OUTPUT"/changes.txt.tmp
echo "Generated on $(date)" >> "$OUTPUT"/changes.txt.tmp

# move things into place, don't change timestamp unless there are changes
# so that if-modified-since etc works
if [ ! -e "$OUTPUT"/changes.txt ] || ! cmp <(grep -v "Generated on" "$OUTPUT"/changes.txt.tmp) <(grep -v "Generated on" "$OUTPUT"/changes.txt) 2>/dev/null; then
    mv "$OUTPUT"/changes.txt.tmp "$OUTPUT"/changes.txt
fi
rm -f "$OUTPUT"/changes.txt.tmp
