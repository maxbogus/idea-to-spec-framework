"""Проверка формата ledger: измеренные факты и принятые решения.

Зачем. `prompts/ledger/findings.jsonl` и `prompts/ledger/decisions.jsonl` —
источник правды о том, что измерено, а что решено. Если формат разъедется,
записи перестанут читаться машиной (следующая сессия не сможет опереться на
измерения) и потеряют смысл.

Ledger — append-only: записи не переписываются задним числом, новые
измерения добавляются. Поэтому проверка строгая к структуре, но не к
содержанию.

Проверяется:
- каждая строка — валидный JSON-объект;
- у каждой записи есть `id`, `date` (YYYY-MM-DD) и `topic`;
- `id` уникален в пределах файла;
- в findings есть `finding` и `evidence` (факт без измерения — не факт);
- в decisions есть `decision`, `rationale` и `consequence`.

Запуск: `python3 scripts/check_ledger.py` или `make check-ledger`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: Корень репозитория (скрипт лежит в `scripts/`).
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Каталог с ledger.
LEDGER_DIR = REPO_ROOT / "prompts" / "ledger"

#: Требуемые поля по типу записи.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "findings": ("id", "date", "topic", "finding", "evidence", "action"),
    "decisions": ("id", "date", "topic", "decision", "rationale", "consequence"),
}

#: Формат даты.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_file(path: Path, kind: str) -> list[str]:
    """Проверить один файл ledger.

    Args:
        path: Путь к файлу.
        kind: Тип записи (`findings` или `decisions`).

    Returns:
        Список проблем (пустой, если файл корректен).
    """
    problems: list[str] = []
    if not path.exists():
        return [f"{path.name}: файл не найден"]

    required = REQUIRED_FIELDS[kind]
    seen_ids: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}:{number}: невалидный JSON ({exc})")
            continue
        if not isinstance(record, dict):
            problems.append(f"{path.name}:{number}: запись не объект")
            continue

        for field in required:
            if not record.get(field):
                problems.append(f"{path.name}:{number}: нет поля {field!r}")

        date = str(record.get("date") or "")
        if date and not _DATE_RE.match(date):
            problems.append(f"{path.name}:{number}: дата {date!r} не в формате YYYY-MM-DD")

        record_id = str(record.get("id") or "")
        if record_id:
            if record_id in seen_ids:
                problems.append(f"{path.name}:{number}: повторяющийся id {record_id!r}")
            seen_ids.add(record_id)
    return problems


def main() -> int:
    """Проверить все файлы ledger.

    Returns:
        0 — все файлы корректны; 1 — есть проблемы.
    """
    problems: list[str] = []
    for kind in REQUIRED_FIELDS:
        problems.extend(check_file(LEDGER_DIR / f"{kind}.jsonl", kind))

    if problems:
        print("check-ledger: FAILED")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print("check-ledger: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
