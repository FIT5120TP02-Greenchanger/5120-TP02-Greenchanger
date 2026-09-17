#!/usr/bin/env bash
# Tests for publish-frontend.sh.
#
# The case that matters is the third one: when the copy fails, the live directory
# must still be serving the previous release. An earlier version of this sequence
# moved the old release out of the way *before* copying the new one in, which left
# the site empty for the duration of the copy and permanently empty if it failed.
#
# Each case runs the script as a separate process so `set -e` behaves exactly as it
# does under SSM. Calling it as `if publish; then` would put it in a condition
# context, where bash suppresses `set -e` inside -- the test would pass while
# proving nothing.
set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/publish-frontend.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

check() { # check DESCRIPTION EXPECTED ACTUAL
  if [ "$2" = "$3" ]; then
    echo "  ok    $1"
  else
    echo "  FAIL  $1: expected '$2', got '$3'"
    fails=$((fails + 1))
  fi
}

mkdir -p "$TMP/dist" "$TMP/root"
echo v1 > "$TMP/dist/index.html"

echo "a first deploy onto a host with no web directory"
bash "$SCRIPT" "$TMP/dist" "$TMP/root" >/dev/null 2>&1
check "exit status" 0 $?
check "published" v1 "$(cat "$TMP/root/web/index.html")"

echo "a normal deploy over an existing release"
echo v2 > "$TMP/dist/index.html"
bash "$SCRIPT" "$TMP/dist" "$TMP/root" >/dev/null 2>&1
check "exit status" 0 $?
check "published" v2 "$(cat "$TMP/root/web/index.html")"
check "previous release kept" v1 "$(cat "$TMP/root/web.old/index.html")"

echo "a failed copy leaves the live release serving"
echo LIVE > "$TMP/root/web/index.html"
mv "$TMP/dist" "$TMP/dist-gone"
bash "$SCRIPT" "$TMP/dist" "$TMP/root" >/dev/null 2>&1
check "exit status" 1 $?
check "live release untouched" LIVE "$(cat "$TMP/root/web/index.html")"

echo "deploying again after a failure"
mv "$TMP/dist-gone" "$TMP/dist"
echo v3 > "$TMP/dist/index.html"
bash "$SCRIPT" "$TMP/dist" "$TMP/root" >/dev/null 2>&1
check "exit status" 0 $?
check "published" v3 "$(cat "$TMP/root/web/index.html")"

if [ "$fails" -gt 0 ]; then
  echo "$fails check(s) failed"
  exit 1
fi
echo "all checks passed"
