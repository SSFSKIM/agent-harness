#!/bin/sh
# Build the Claude worker runtime (cc-appserver) absorbed into this monorepo.
#
# Run once after cloning (and after pulling changes under worker-runtime/). The
# Director's `--worker claude` runtime invokes worker-runtime/app-server/dist/bin.js,
# which this produces. Both node_modules/ and the tsc build output (dist/) are
# gitignored — they are generated, never committed.
#
# Build order matters: the app-server's tsc needs cc-harness's emitted types, so the
# harness package is built first (its `prepack` does not fire on `npm install`, hence
# the explicit `npm run build`); the app-server's `prepare` then auto-builds dist/bin.js
# on its own install.
set -e
here=$(cd "$(dirname "$0")" && pwd)

echo "[1/2] building cc-harness…"
( cd "$here/harness" && npm install && npm run build )

echo "[2/2] building cc-appserver (prepare auto-builds dist/bin.js)…"
( cd "$here/app-server" && npm install )

echo "done — worker runtime at $here/app-server/dist/bin.js"
