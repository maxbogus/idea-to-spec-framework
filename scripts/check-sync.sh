#!/usr/bin/env bash
# Verify that skills, methods, templates and scripts are wired into the pipeline,
# that every role/artifact has an owner in handout-index.md, that every gate has
# a checklist, and that all three modes (auto / chat / hybrid) are documented.
# Usage: scripts/check-sync.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0

# 1. Every skill is referenced by a role prompt or the start prompt.
# Скил — каталог `skills/<name>/SKILL.md`; роль ссылается на путь целиком.
for f in skills/*/SKILL.md; do
  name="$(basename "$(dirname "$f")")"
  if ! grep -rq "skills/$name/SKILL.md" prompts/roles prompts/start.md; then
    echo "UNUSED SKILL: $name"
    fail=1
  fi
done

# 2. Every template is referenced by the start prompt or the diagram skill.
for f in templates/*; do
  b="$(basename "$f")"
  if ! grep -q "$b" prompts/start.md skills/diagram-generation/SKILL.md; then
    echo "UNREFERENCED TEMPLATE: $b"
    fail=1
  fi
done

# 3. Every shell script is referenced by the Makefile.
for f in scripts/*.sh; do
  b="$(basename "$f")"
  if ! grep -q "$b" Makefile; then
    echo "UNREFERENCED SCRIPT: $b"
    fail=1
  fi
done

# 3c. The cross-reference validator must be wired into the Makefile.
# Проверяет, что идентификаторы в схемах ролей согласованы между собой
# (иначе модель не сможет дать идентификатор, который требуют).
if ! grep -q "check_cross_refs.py" Makefile; then
  echo "UNREFERENCED SCRIPT: check_cross_refs.py"
  fail=1
fi

# 3b. The ledger validator must be wired into the Makefile.
# Ledger хранит измеренные факты и принятые решения; без проверки формата
# он молча перестаёт читаться машиной.
if ! grep -q "check_ledger.py" Makefile; then
  echo "UNREFERENCED SCRIPT: check_ledger.py"
  fail=1
fi

# 3a. Every python script is referenced by the Makefile or an eval config.
# Без этого новый guardrail можно добавить и забыть подключить — он молча
# ничего не проверяет, а гейт об этом не сообщает.
# Часть скриптов подключается не через Makefile, а через конфиги promptfoo
# (exec-провайдер и transformVars), поэтому ищем оба места.
for f in scripts/*.py; do
  b="$(basename "$f")"
  if grep -q "$b" Makefile; then continue; fi
  if grep -rq "$b" eval/*.yaml; then continue; fi
  echo "UNREFERENCED SCRIPT: $b"
  fail=1
done

# 4. All three modes are documented in the start prompt.
for m in auto chat hybrid; do
  if ! grep -qi "\\b$m\\b" prompts/start.md; then
    echo "MODE NOT DOCUMENTED: $m"
    fail=1
  fi
done

# 5. Every role prompt has a row in handout-index.md.
for f in prompts/roles/*.md; do
  b="$(basename "$f")"
  if ! grep -q "$b" handout-index.md; then
    echo "ROLE NOT IN INDEX: $b"
    fail=1
  fi
done

# 6. Every method is used by a role, the start prompt or the index.
for f in methods/*.md; do
  b="$(basename "$f")"
  if ! grep -rq "$b" prompts/roles prompts/start.md handout-index.md; then
    echo "UNUSED METHOD: $b"
    fail=1
  fi
done

# 7. Every artifact template has an owner-role in handout-index.md.
for f in templates/*.md; do
  b="$(basename "$f" .md)"
  a="${b%-template}"
  if ! grep -q "$a" handout-index.md; then
    echo "ARTIFACT WITHOUT OWNER: $f"
    fail=1
  fi
done

# 8. Every gate has a checklist in prompts/gate-checklists.md.
# Чеклисты вынесены из rules.md, а потом из orchestrator-guide.md: и в общих
# правилах, и в гайде модель переключалась в режим «заполни чек-лист» вместо
# ответа своей роли (измерено на eval-прогоне qwen2.5:7b).
for gate in "BA-gate" "SA-gate" "Spec-gate"; do
  if ! grep -q "Чеклист $gate" prompts/gate-checklists.md; then
    echo "GATE CHECKLIST MISSING: $gate"
    fail=1
  fi
done

# 8a. Чек-листы гейтов не должны попадать в промпт, который видит модель.
for f in prompts/rules.md prompts/orchestrator-guide.md; do
  if grep -qE '^## Чеклист (BA|SA|Spec)-gate' "$f"; then
    echo "GATE CHECKLIST IN MODEL PROMPT: $f"
    fail=1
  fi
done

# 9. Реестр скилов: каждый скил описан, версия semver, зависимости резолвятся.
# Без этого вызова реестр молча разъедется с каталогом skills/: скил добавлен,
# записи нет — и метаданные перестанут быть источником правды.
if ! uv run python scripts/check_skills_registry.py; then
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "check-sync: OK"
else
  echo "check-sync: FAILED" >&2
  exit 1
fi
