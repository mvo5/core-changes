# Generate changes for the core snap

This repository provides the tool to generate changelogs for
the snapd core snap. It can be run inside cron or as a standalone
tool.

## Usage

Run:

    $ bin/gen-core-changes --markdown /path/to/directory/with/core/snaps

It will generate a markdown document that contains the changes
for each core.

It also supported `--html` to generate a html changelog.

## Cron

There is a helper shell script that can be put into cron. Just
add the following to your crontab:

    06 10 * * * ~/core-changelogs/bin/cron.sh

This will build the archive and generate the changes automatically.
You may want to customize the output path in there.

## Development

Run the tests via:

    python -m unittests discover

