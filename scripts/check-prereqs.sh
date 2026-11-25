#!/usr/bin/env bash
# Preflight: verify the toolchain required to use the workshop repo.
# Usage: scripts/check-prereqs.sh
# Checks: node, make, templates/mermaid-config.json and mmdc (mermaid-cli)
# version >= MMDC_MIN. Exits non-zero on any failure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MMDC_MIN="${MMDC_MIN:-12.0.0}"
MMDC="${MMDC:-mmdc}"

fail=0
ok()  { echo "  OK:   $*"; }
bad() { echo "  FAIL: $*" >&2; fail=1; }

# semver_ge <have> <need> -> returns 0 if have >= need, 1 otherwise.
semver_ge() {
  local have="${1%%-*}" need="$2"
  local -a h n
  IFS=. read -r -a h <<< "$have"
  IFS=. read -r -a n <<< "$need"
  local i hv nv
  for i in 0 1 2; do
    hv="${h[$i]:-0}"
    nv="${n[$i]:-0}"
    if [ "$hv" -gt "$nv" ]; then return 0; fi
    if [ "$hv" -lt "$nv" ]; then return 1; fi
  done
  return 0
}

echo "== Preflight: окружение воркшопа =="

# 1. node
if command -v node >/dev/null 2>&1; then
  ok "node $(node --version)"
else
  bad "node не найден (нужен Node.js 18+; рекомендуем nvm)"
fi

# 2. mmdc (mermaid-cli) + version
if command -v "$MMDC" >/dev/null 2>&1; then
  mmdc_ver="$("$MMDC" --version 2>/dev/null | head -1 | tr -d 'v ')"
  if semver_ge "$mmdc_ver" "$MMDC_MIN"; then
    ok "$MMDC $mmdc_ver (>= $MMDC_MIN)"
  else
    bad "$MMDC $mmdc_ver < $MMDC_MIN — обнови: npm i -g @mermaid-js/mermaid-cli@^12"
  fi
else
  bad "$MMDC не найден — установи: npm i -g @mermaid-js/mermaid-cli@^12"
fi

# 3. make
if command -v make >/dev/null 2>&1; then
  ok "make $(make --version 2>/dev/null | head -1 | awk '{print $3}')"
else
  bad "make не найден (нужен GNU make)"
fi

# 4. mermaid config used by the deterministic renderer
if [ -f "templates/mermaid-config.json" ]; then
  ok "templates/mermaid-config.json"
else
  bad "templates/mermaid-config.json не найден"
fi

if [ "$fail" -eq 0 ]; then
  echo "== Preflight: OK =="
else
  echo "== Preflight: FAILED — исправь пункты выше ==" >&2
  exit 1
fi
