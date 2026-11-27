"""Проверка машинно-читаемых схем ответов ролей (P4).

Зачем. `prompts/schemas.yaml` — источник правды о верхнеуровневых полях
ответа. Без проверки он разъедется с промптами и eval-контрактами: именно
так `expected_fields` разошёлся со схемой (PM-01 ждал `baseline`, PM-02 —
`objections`, хотя это вложенные поля; F037).

Проверяется:
- у каждого поля схемы есть пара в JSON-примере промпта, типы совпадают;
- в примере нет полей, которых нет в схеме;
- `expected_fields` каждого eval-кейса — поле верхнего уровня своей роли;
- типы полей и элементов массивов — из допустимого набора.

Запуск: `python3 scripts/check_role_schemas.py` или `make check-schemas`.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.paths import REPO_ROOT  # noqa: E402
from idea_to_spec.role_schemas import SCHEMAS_YAML, check_all  # noqa: E402


def main() -> int:
    """Точка входа CLI.

    Returns:
        0 — контракт согласован; 1 — есть расхождения.
    """
    problems = check_all(REPO_ROOT)
    if problems:
        print(f"check-schemas: FAILED — {len(problems)} проблем:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"check-schemas: OK ({SCHEMAS_YAML.as_posix()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
