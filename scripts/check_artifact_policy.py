"""Лёгкий guardrail для артефактов прогона (`output/<run-id>/`).

Назначение. Артефакты спецификации могут содержать примеры: телефон,
email, номер карты, ключ API. Это не всегда ошибка — но это всегда
«требует human-review», потому что в воркшопе за артефактом стоит
человек, который решает, можно ли такое публиковать.

Поэтому скрипт **не роняет гейт**: он печатает предупреждения и завершает
работу с кодом 0. Решение «пустить или не пустить» принимает человек.

Что проверяется:
- email-адреса;
- телефонные номера (в формате +7 916 237-45-00 и подобных);
- длинные числовые последовательности (номер карты);
- присвоенные ключи/секреты (`api_key = ...`, `password: ...`).

Запуск: `python3 scripts/check_artifact_policy.py output/auto-002` или
`make check-policy RUN=auto-002`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Артефакты, которые проверяются: текстовые файлы прогона.
SCANNED_GLOBS: tuple[str, ...] = ("*.md", "diagrams/*.mmd", "diagrams/*.bpmn")

#: Правила: имя -> (регулярка, описание находки).
#: Регулярки намеренно консервативны: лучше пропустить находку, чем
#: завалить гейт ложными срабатываниями на обычном тексте спецификации.
RULES: dict[str, tuple[re.Pattern[str], str]] = {
    "email": (
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        "email-адрес",
    ),
    "phone": (
        re.compile(r"(?<![\w-])(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?![\w-])"),
        "номер телефона",
    ),
    "card": (
        re.compile(r"(?<![\d-])\d{13,19}(?![\d-])"),
        "длинная числовая последовательность (похоже на номер карты)",
    ),
    "secret": (
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|bearer|token)\b\s*[:=]\s*\S+"
        ),
        "присвоенный ключ или секрет",
    ),
}

#: Строки, где находка ожидаема и потому не показывается.
#: Спецификация регулярно упоминает «персональные данные», «токены» и т. п.
NOISE_MARKERS: tuple[str, ...] = (
    "персональные данные",
    "персональных данных",
    "защищённые",
)


def _scan_text(text: str) -> list[str]:
    """Найти подозрительные места в тексте.

    Args:
        text: Текст артефакта.

    Returns:
        Список описаний находок (без указания строк).
    """
    lowered = text.lower()
    hits: list[str] = []
    for name, (pattern, label) in RULES.items():
        for match in pattern.finditer(text):
            found = match.group(0)
            if (
                name == "secret"
                and any(marker in lowered for marker in NOISE_MARKERS)
                and found.lower().endswith(("данные", "данных"))
            ):
                # «токены: персональные» и подобное — не секрет.
                continue
            if name == "phone" and re.fullmatch(r"\d{2}[-.\s]?\d{2}", found.strip()):
                # Короткие числа вида «10 20» — не телефон.
                continue
            hits.append(f"{label}: «{found[:40]}»")
            break
    return hits


def check_policy(run_dir: Path) -> list[str]:
    """Проверить артефакты прогона на подозрительные находки.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).

    Returns:
        Список предупреждений (пустой список — находок нет).
    """
    if not run_dir.is_dir():
        return [f"нет каталога прогона: {run_dir}"]
    warnings: list[str] = []
    for pattern in SCANNED_GLOBS:
        for path in sorted(run_dir.glob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            for hit in _scan_text(text):
                warnings.append(f"{path.name}: {hit}")
    return warnings


def main(argv: list[str]) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки (путь к прогону).

    Returns:
        0 — всегда: находки не роняют гейт, они требуют human-review.
    """
    if len(argv) < 2:
        print("Использование: check_artifact_policy.py <output/run-id>")
        return 2
    run_dir = Path(argv[1])
    warnings = check_policy(run_dir)
    if not warnings:
        print(f"check-policy: OK ({run_dir})")
        return 0
    print(f"check-policy: требует human-review ({run_dir}) — {len(warnings)} находок:")
    for warning in warnings:
        print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
