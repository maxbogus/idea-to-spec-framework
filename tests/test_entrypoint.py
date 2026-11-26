"""Контракт точки входа: `prompts/start.md` — единственный вход агента."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
START = REPO_ROOT / "prompts" / "start.md"


def test_entrypoint_has_steps() -> None:
    """Точка входа содержит шаги режима и каркаса."""

    text = START.read_text(encoding="utf-8")
    assert "## Шаг 0. Режим" in text
    assert "## Шаг 2. Каркас" in text
    assert "prompts/orchestrator.md" in text
    assert "prompts/gate-checklists.md" in text


def test_referenced_prompts_exist() -> None:
    """Каждый `prompts/*.md`, упомянутый во входе, существует."""

    text = START.read_text(encoding="utf-8")
    references = set(re.findall(r"prompts/[A-Za-z0-9_./-]+\.md", text))
    assert references
    missing = [reference for reference in references if not (REPO_ROOT / reference).is_file()]
    assert not missing, f"нет файлов: {sorted(missing)}"
