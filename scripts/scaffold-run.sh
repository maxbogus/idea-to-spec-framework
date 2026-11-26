#!/usr/bin/env bash
# Materialize a run scaffold in output/<run-id>/ from templates/.
#
# Usage: scripts/scaffold-run.sh <run-id> [base|full|all] [packs] [out-root]
#
# out-root по умолчанию `output`. Абсолютный путь используется как есть:
# артефакты прогона можно держать вне каталога фреймворка (например,
# `specs/` в проекте-потребителе).
#
# Diagrams come in tiers (see prompts/start.md, Step 2):
#   base     — always created: use-case, sequence, c4-context, c4-container;
#   extended — created with "full" or "all": er, dfd-*, c4-component,
#              c4-deployment, bpmn-process, activity, gantt;
#   packs    — copied only when named: behavior, domain, process, ux, data,
#              ai, infra, architecture (see `prompts/start.md`, блок «Паки»).
#
# Generating every diagram at once burns the context window and blurs
# quality; the base tier is the default on purpose.
#
# Backward compatibility: `scaffold-run.sh <run-id> <tier> [out-root]` keeps
# working — a third argument with a slash is treated as out-root, not a pack.
set -euo pipefail

RUN_ID="${1:-}"
TIER="${2:-base}"
PACKS_ARG="${3:-}"
OUT_ROOT="${4:-output}"

if [ -z "$RUN_ID" ]; then
  echo "Usage: scripts/scaffold-run.sh <run-id> [base|full|all] [packs] [out-root]" >&2
  exit 1
fi

if ! [[ "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ERROR: invalid run-id '$RUN_ID' (allowed: letters, digits, dot, underscore, hyphen)" >&2
  exit 1
fi

# Легаси: третий аргумент раньше был out-root (путь всегда содержит '/').
if [ -n "$PACKS_ARG" ] && [[ "$PACKS_ARG" == */* ]]; then
  OUT_ROOT="$PACKS_ARG"
  PACKS_ARG=""
fi

case "$TIER" in
  base|full|all) ;;
  *)
    echo "ERROR: invalid tier '$TIER' (allowed: base, full, all)" >&2
    exit 1
    ;;
esac


ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TPL="$ROOT/templates"
case "$OUT_ROOT" in
  /*|[A-Za-z]:[\\/]*) OUT="$OUT_ROOT/$RUN_ID" ;;
  *) OUT="$ROOT/$OUT_ROOT/$RUN_ID" ;;
esac

# Паки диаграмм: имя пака -> файлы скелетов. Каталог паков — prompts/start.md,
# блок «Паки»; согласованность проверяет tests/test_diagram_catalog.py.
# Проверка имён идёт до создания каталогов: неизвестный пак не оставляет мусор.
ALL_PACKS="behavior domain process ux data ai infra architecture"

pack_diagrams() {
  # Вернуть список файлов пака; неизвестный пак — код 1.
  case "$1" in
    behavior) echo "state.mmd" ;;
    domain) echo "domain-map.mmd event-storming.mmd" ;;
    process) echo "dmn.mmd sipoc.mmd" ;;
    ux) echo "service-blueprint.mmd" ;;
    data) echo "data-lineage.mmd" ;;
    ai) echo "rag-pipeline.mmd vector-schema.mmd agent-workflow.mmd prompt-flow.mmd feedback-loop.mmd" ;;
    infra) echo "network-topology.mmd iac.mmd" ;;
    architecture) echo "c4-code.mmd" ;;
    *) return 1 ;;
  esac
}

if [ "$TIER" = "all" ]; then
  packs="$ALL_PACKS"
else
  packs="$(echo "$PACKS_ARG" | tr ',' ' ')"
fi

for p in $packs; do
  if ! pack_diagrams "$p" >/dev/null; then
    echo "ERROR: unknown pack '$p' (allowed: $ALL_PACKS)" >&2
    exit 1
  fi
done

mkdir -p "$OUT/diagrams"

artifacts="brief open-questions personas jtbd business-requirements functional-requirements nonfunctional-requirements use-cases spec traceability-matrix risk-register human-oversight-plan validation-report hallucination-log cjm run-report"

# Базовый уровень диаграмм — создаётся всегда.
base_diagrams="use-case.mmd sequence.mmd c4-context.mmd c4-container.mmd"
# Расширенный уровень — при full или all.
extended_diagrams="er.mmd dfd-context.mmd dfd-level1.mmd dfd-level2.mmd dfd-level3.mmd c4-component.mmd c4-deployment.mmd bpmn-process.mmd activity.mmd gantt.mmd"

created=0
skipped=0

for a in $artifacts; do
  case "$a" in
    brief) src="$TPL/brief-template.md" ;;
    spec)  src="$TPL/spec-template.md" ;;
    *)     src="$TPL/$a.md" ;;
  esac
  if [ ! -f "$src" ]; then
    echo "ERROR: template not found: $src" >&2
    exit 1
  fi
  dst="$OUT/$a.md"
  if [ -e "$dst" ]; then
    skipped=$((skipped + 1))
  else
    cp "$src" "$dst"
    created=$((created + 1))
  fi
done

copy_diagram() {
  # Скопировать один скелет диаграммы, если он есть в templates/.
  local name="$1"
  local src="$TPL/$name"
  if [ ! -f "$src" ]; then
    echo "ERROR: template not found: $src" >&2
    exit 1
  fi
  local dst="$OUT/diagrams/$name"
  if [ -e "$dst" ]; then
    skipped=$((skipped + 1))
  else
    cp "$src" "$dst"
    created=$((created + 1))
  fi
}

for d in $base_diagrams; do
  copy_diagram "$d"
done

if [ "$TIER" != "base" ]; then
  for d in $extended_diagrams; do
    copy_diagram "$d"
  done
  # Канонический BPMN 2.0 XML копируется отдельно: templates/*.mmd его не покрывает.
  copy_diagram "bpmn-process.bpmn"
fi

for p in $packs; do
  for d in $(pack_diagrams "$p"); do
    copy_diagram "$d"
  done
done

echo "Scaffold: $OUT (tier=$TIER, packs=${packs:-none}, created=$created, skipped=$skipped)"
