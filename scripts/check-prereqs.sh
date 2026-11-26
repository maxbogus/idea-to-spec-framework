#!/usr/bin/env bash
# Preflight: verify the toolchain required to use the framework.
# Usage: scripts/check-prereqs.sh  (переменные: PYTHON, MMDC, MMDC_MIN)
# Checks: node, mmdc >= MMDC_MIN, GNU make, python >= 3.11, uv, git,
# bash version (warning) and templates/mermaid-config.json. promptfoo is
# optional (eval only) and reported as HINT. Exits non-zero on any failure.
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

# 3. make — только GNU: Makefile использует .DEFAULT_GOAL, MAKEFILE_LIST,
# CURDIR и $(if). BSD make (macOS по умолчанию) падает ещё до первой цели.
if command -v make >/dev/null 2>&1; then
  make_line="$(make --version 2>/dev/null | head -1 || true)"
  case "$make_line" in
    *"GNU Make"*) ok "make: $make_line" ;;
    *)
      bad "make не GNU ($make_line) — macOS: brew install make, затем запускай gmake"
      ;;
  esac
else
  bad "make не найден (нужен GNU make)"
fi

# 4. python >= 3.11 (Makefile вызывает $(PYTHON); на Windows это `python`)
PY="${PYTHON:-python3}"
if command -v "$PY" >/dev/null 2>&1; then
  py_ver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  if semver_ge "$py_ver" "3.11"; then
    ok "$PY $py_ver (>= 3.11)"
  else
    bad "$PY $py_ver < 3.11 — обнови Python или задай PYTHON=<путь>"
  fi
else
  bad "$PY не найден — на Windows: make PYTHON=python ..."
fi

# 5. uv — eval-обвязка и проверки запускаются через `uv run`
if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"
else
  bad "uv не найден — https://docs.astral.sh/uv/"
fi

# 6. git — check-runs берёт отслеживаемые прогоны (fallback: каталоги с диска)
if command -v git >/dev/null 2>&1; then
  ok "git $(git --version 2>/dev/null | awk '{print $3}')"
else
  bad "git не найден — check-runs будет проверять прогоны с диска"
fi

# 7. bash: скрипты совместимы с 3.2, но на 3.2 часть диагностики беднее
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
  echo "  WARN: bash ${BASH_VERSION} (< 4) — macOS: brew install bash (скрипты совместимы)"
fi

# 8. promptfoo нужен только для eval: установка — make eval-setup
if [ -e "node_modules/.bin/promptfoo" ]; then
  ok "promptfoo: node_modules/.bin/promptfoo"
else
  echo "  HINT: promptfoo не установлен — make eval-setup (нужен для make eval / make eval-mock)"
fi

# 9. mermaid config used by the deterministic renderer
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
