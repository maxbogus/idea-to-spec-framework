"""Проверить, что отчёт реального прогона соответствует текущему набору.

Зачем. `eval/cases/roles.jsonl` и `docs/evaluation/eval-qwen3-8b.json` живут
в разных местах и меняются независимо. Набор расширили — а отчёт остался от
старого прогона: расхождение видно только глазами, при чтении чисел.

Раньше такого гейта не было, и молчаливое устаревание отчёта не ловилось
(проверялось только совпадение списка провалов с отчётом, но не состав).

Проверяется:
- отчёт существует;
- число кейсов в отчёте совпадает с числом кейсов в наборе;
- каждый кейс набора присутствует в отчёте.

Гейт НЕ роняет сборку: несоответствие — это human-review (как
`check_artifact_policy.py`), потому что полный реальный прогон идёт
отдельной волной и не должен блокировать работу над набором.

Запуск: `python3 scripts/check_eval_report_fresh.py` или
`make check-eval-report`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from idea_to_spec.paths import EVAL_CASES_FILE, EVAL_REPORT_FILE  # noqa: E402


def _case_ids() -> list[str]:
    """Собрать идентификаторы кейсов из eval-набора.

    Returns:
        Список идентификаторов в порядке файла.
    """
    ids: list[str] = []
    for line in EVAL_CASES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        ids.append(str(json.loads(item["vars"]["contract"])["id"]))
    return ids


def _report_ids() -> set[str]:
    """Собрать идентификаторы кейсов из отчёта реального прогона.

    Returns:
        Множество идентификаторов, присутствующих в отчёте.
    """
    payload = json.loads(EVAL_REPORT_FILE.read_text(encoding="utf-8"))
    results = payload.get("results")
    items = results.get("results") if isinstance(results, dict) else results
    if not isinstance(items, list):
        return set()
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        vars_block = item.get("vars")
        if isinstance(vars_block, dict) and vars_block.get("id"):
            ids.add(str(vars_block["id"]))
    return ids


def check() -> list[str]:
    """Сверить состав набора и отчёта.

    Returns:
        Список расхождений (пустой, если отчёт соответствует набору).
    """
    if not EVAL_REPORT_FILE.exists():
        return [
            f"нет отчёта реального прогона: {EVAL_REPORT_FILE} "
            "(запустите `make eval`)"
        ]

    case_ids = _case_ids()
    report_ids = _report_ids()

    problems: list[str] = []
    if len(report_ids) != len(case_ids):
        problems.append(
            f"отчёт устарел: в наборе {len(case_ids)} кейсов, в отчёте "
            f"{len(report_ids)} — перезапустите `make eval`"
        )
    missing = [cid for cid in case_ids if cid not in report_ids]
    if missing:
        problems.append(
            f"в отчёте нет кейсов: {', '.join(missing)} — перезапустите `make eval`"
        )
    return problems


def main() -> int:
    """Точка входа CLI.

    Returns:
        0 — расхождений нет (или отчёт устарел: human-review, не провал).
    """
    problems = check()
    if not problems:
        print("check-eval-report: отчёт соответствует набору")
        return 0
    print("check-eval-report: расхождение отчёта и набора (human-review)")
    for problem in problems:
        print(f"  - {problem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
