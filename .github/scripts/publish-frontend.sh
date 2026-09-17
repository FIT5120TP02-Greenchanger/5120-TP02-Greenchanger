#!/usr/bin/env bash
# Publish a built frontend into the directory nginx serves.
#
# The release is staged in web.new and swapped in only once the copy has fully
# succeeded, so a failed build or copy leaves the live site untouched rather
# than half-replaced. The previous release stays in web.old.
#
# The swap is two renames, so there is a sub-millisecond window where web does
# not exist. If that ever matters, make web a symlink into a releases/ directory
# and swap it with a single `mv -T`, which is one atomic rename(2).
#
# Lives here rather than inline in deploy.yml so test-publish-frontend.sh can run
# the real thing -- a copy of the sequence pasted into a test would drift from
# the sequence that actually deploys.
set -euo pipefail

DIST=${1:?usage: publish-frontend.sh DIST_DIR SERVE_ROOT [OWNER]}
ROOT=${2:?usage: publish-frontend.sh DIST_DIR SERVE_ROOT [OWNER]}
OWNER=${3:-}

rm -rf "$ROOT/web.new"
cp -r "$DIST" "$ROOT/web.new"
# An `[ -n "$OWNER" ] && chown ...` list would exit the script under `set -e`
# whenever OWNER is empty, because the failed test becomes the list's status.
if [ -n "$OWNER" ]; then chown -R "$OWNER" "$ROOT/web.new"; fi

rm -rf "$ROOT/web.old"
if [ -d "$ROOT/web" ]; then mv "$ROOT/web" "$ROOT/web.old"; fi

mv "$ROOT/web.new" "$ROOT/web" || {
  echo "swap failed, restoring the previous release"
  mv "$ROOT/web.old" "$ROOT/web"
  exit 1
}

echo "published to $ROOT/web"
