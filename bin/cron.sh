#!/bin/sh

BASE=$(dirname $0)/..

PATH=$PATH:$BASE/bin

OUTPUT=~/public_html/core-changes



# ensure we have an archive of cores
(cd $BASE/archive ; snap download --stable core 2>/dev/null)

# generate the changes
gen-core-changes.py $BASE/archive > $OUTPUT/changes.txt

echo "" >> $OUTPUT/changes.txt
echo "Generate $(date)" >> $OUTPUT/changes.txt

