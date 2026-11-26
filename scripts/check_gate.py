"""Проверка ответа гейта: `checks[]` по чеклисту (`prompts/gate-checklists.yaml`).

Зачем отдельный скрипт. Гейт возвращает вердикт по каждому пункту чеклиста.
Пока вердикт жил свободным списком `missing`, «гейт-печати» (BA-gate сказал
`passed` при четырёх незакрытых пунктах) нельзя было отличить от реального
прохождения: не за что зацепиться. Здесь у ответа есть контракт, и он
проверяется одинаково в прогоне (`check_run`), в eval (`gate_contract`) и
руками (`make check-gate`).

Проверяется:
- гейт объявлен в `prompts/gate-checklists.yaml`;
- `checks` содержит ровно по одной записи на каждый id чеклиста;
- статус пункта — `pass` / `fail` / `na`; `na` только для условных пунктов
  и только с причиной;
- `pass` и `fail` не пустые: без доказательства вердикта нет;
- `missing` совпадает с множеством `fail`;
- `status=passed` несовместим с `fail`, `status=failed` требует хотя бы один;
- `return_to` допустим для этого гейта, при `failed` — обязателен.

Запуск:
    python3 scripts/check_gate.py output/auto-005/validation-report.md
    python3 scripts/check_gate.py gate.json --gate BA-gate
    make check-gate FILE=gate.json GATE=BA-gate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

#: Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.gate_checklists import (  # noqa: E402
    extract_gate_payloads,
    validate_gate_payload,
)


def check_file(path: Path, expected_gate: str = "") -> list[str]:
    """Проверить файл с ответом гейта (JSON или markdown-отчёт).

    Args:
        path: Путь к JSON-файлу или markdown-отчёту с разделом «Гейты».
        expected_gate: Ожидаемое имя гейта (пусто — доверять ответу).

    Returns:
        Список проблем; пустой список — контракт выполнен.
    """
    if not path.is_file():
        return [f"файл не найден: {path}"]

    if path.suffix.lower() in {".md", ".markdown"}:
        text = path.read_text(encoding="utf-8")
        payloads, problems = extract_gate_payloads(text)
        if not payloads and not problems:
            return [f"{path}: в разделе «Гейты» нет ни одного ответа гейта"]
        for gate_payload in payloads:
            problems.extend(validate_gate_payload(gate_payload, expected_gate))
        return problems

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path}: невалидный JSON ({exc})"]
    return validate_gate_payload(payload, expected_gate)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки.

    Returns:
        0 — контракт выполнен; 1 — найдены проблемы; 2 — неверные аргументы.
    """
    parser = argparse.ArgumentParser(description="Проверка ответа гейта по чеклисту")
    parser.add_argument("file", type=Path, help="JSON-ответ гейта или отчёт с разделом «Гейты»")
    parser.add_argument("--gate", default="", help="Ожидаемое имя гейта (BA-gate, SA-gate, Spec-gate)")
    args = parser.parse_args(argv)

    problems = check_file(args.file, args.gate)
    if not problems:
        print(f"check-gate: OK ({args.file})")
        return 0
    print(f"check-gate: FAILED ({args.file}) — {len(problems)} проблем:")
    for problem in problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
