"""Контракт: секции spec.md, на которые ссылаются диаграммы, есть в шаблоне спеки."""

from __future__ import annotations

import re

from idea_to_spec.paths import REPO_ROOT

#: Ссылки вида `spec.md §6`, `§9` в skill диаграмм.
SECTION_REF_RE = re.compile(r"§(\d+)")
#: Заголовки секций вида `## 9. Архитектура`.
SECTION_HEAD_RE = re.compile(r"^##\s+(\d+)\.", re.MULTILINE)


def _referenced_sections() -> set[int]:
    """Номера секций spec.md, на которые ссылается diagram-generation.

    Returns:
        Множество номеров (например, {6, 9}).
    """
    text = (REPO_ROOT / "skills" / "diagram-generation.md").read_text(encoding="utf-8")
    return {int(number) for number in SECTION_REF_RE.findall(text)}


def _template_sections() -> set[int]:
    """Номера секций, реально присутствующих в spec-template.md.

    Returns:
        Множество номеров заголовков.
    """
    text = (REPO_ROOT / "templates" / "spec-template.md").read_text(encoding="utf-8")
    return {int(number) for number in SECTION_HEAD_RE.findall(text)}


def test_diagram_source_sections_exist_in_spec_template() -> None:
    """Каждая §N из diagram-generation есть в spec-template.md."""
    referenced = _referenced_sections()
    available = _template_sections()
    assert referenced, "diagram-generation.md не ссылается на секции spec.md"
    missing = referenced - available
    assert not missing, f"В spec-template.md нет секций: {sorted(missing)}"
