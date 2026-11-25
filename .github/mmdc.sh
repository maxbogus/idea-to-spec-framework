#!/usr/bin/env bash
# mmdc wrapper for CI: runs puppeteer with --no-sandbox.
set -euo pipefail

if [ "${1:-}" = "--version" ] || [ "${1:-}" = "-V" ]; then
  exec mmdc "$@"
fi

exec mmdc --puppeteerConfigFile "$(dirname "$0")/puppeteer-config.json" "$@"
