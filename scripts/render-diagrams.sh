#!/usr/bin/env bash
# Render Mermaid .mmd diagrams to PNG with mermaid-cli.
# Usage: scripts/render-diagrams.sh [dir] [mermaid-config.json]
#   dir    defaults to output/auto-001/diagrams
#   config optional mermaid config (e.g. templates/mermaid-config.json)
# Note: BPMN 2.0 (.bpmn) is NOT rendered here; open it in bpmn.io / Camunda.
set -euo pipefail

DIR="${1:-output/auto-001/diagrams}"
CFG="${2:-}"

if ! command -v mmdc >/dev/null 2>&1; then
  echo "ERROR: mmdc (mermaid-cli) not found. Install: npm i -g @mermaid-js/mermaid-cli" >&2
  exit 1
fi

if [ ! -d "$DIR" ]; then
  echo "ERROR: directory not found: $DIR" >&2
  exit 1
fi

shopt -s nullglob
files=("$DIR"/*.mmd)
if [ ${#files[@]} -eq 0 ]; then
  echo "No .mmd files in $DIR"
  exit 0
fi

mmdc_args=(-b white)
if [ -n "$CFG" ]; then
  if [ -f "$CFG" ]; then
    mmdc_args+=(-c "$CFG")
  else
    echo "WARN: config not found, rendering without it: $CFG" >&2
  fi
fi

for f in "${files[@]}"; do
  out="${f%.mmd}.png"
  echo "render: $f -> $out"
  mmdc -i "$f" -o "$out" "${mmdc_args[@]}"
done

echo "Done: ${#files[@]} diagram(s) rendered in $DIR"
