"""Генерация `prompts/gate-checklists.md` из `prompts/gate-checklists.yaml`.

Зачем. Чеклист нужен в двух видах: человеку — читаемый справочник, машине —
стабильные id пунктов. Держать два источника правды нельзя: они разъедутся
(именно это случилось с формулировками гейтов до P1). Поэтому YAML —
источник, markdown — производная, как `skills/INDEX.md` из реестра скилов.

Запуск:
- `python3 scripts/render_gate_checklists.py --write` — перегенерировать;
- `python3 scripts/render_gate_checklists.py --check` — проверить, что не устарел.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.gate_checklists import (  # noqa: E402
    CHECKLISTS_MD,
    check_markdown,
    render_markdown,
)
from idea_to_spec.paths import REPO_ROOT  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки.

    Returns:
        0 — успех; 1 — справочник устарел (в режиме `--check`).
    """
    parser = argparse.ArgumentParser(description="Генерация справочника чеклистов гейтов")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="записать gate-checklists.md")
    mode.add_argument("--check", action="store_true", help="проверить актуальность")
    args = parser.parse_args(argv)

    if args.check:
        problems = check_markdown(args.root)
        if problems:
            print("check-gates: FAILED")
            for problem in problems:
                print(f"  {problem}")
            return 1
        print("check-gates: OK")
        return 0

    (args.root / CHECKLISTS_MD).write_text(render_markdown(args.root), encoding="utf-8")
    print(f"gates-index: записан {CHECKLISTS_MD.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
