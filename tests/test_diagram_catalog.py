"""Контракт: каталог диаграмм согласован между скилом, scaffold и шаблонами.

Зачем. Каталог живёт в четырёх местах: `skills/diagram-generation` (описание),
`scripts/scaffold-run.sh` (что копируется), `scripts/check_dor.py` (что
требуется профилем) и `templates/*.mmd` (что существует). Расхождение
означает, что диаграмма либо не создаётся, либо создаётся без источника.
"""

from __future__ import annotations

import re
from pathlib import Path

from check_dor import BASE_DIAGRAMS, EXTENDED_DIAGRAMS, PACK_DIAGRAMS
from idea_to_spec.paths import REPO_ROOT

SKILL_MD = REPO_ROOT / "skills" / "diagram-generation" / "SKILL.md"
CATALOG_MD = REPO_ROOT / "skills" / "diagram-generation" / "references" / "diagram-catalog.md"
SCAFFOLD = REPO_ROOT / "scripts" / "scaffold-run.sh"
START_MD = REPO_ROOT / "prompts" / "start.md"
HANDOUT = REPO_ROOT / "handout-index.md"
TEMPLATES = REPO_ROOT / "templates"

#: `ALL_PACKS="behavior domain ..."` в scaffold-run.sh.
ALL_PACKS_RE = re.compile(r'^ALL_PACKS="([^"]+)"', re.MULTILINE)
#: Строки `    ai) echo "rag-pipeline.mmd vector-schema.mmd" ;;` в pack_diagrams().
PACK_CASE_RE = re.compile(r"^\s{4}([a-z]+)\)\s*echo\s+\"([^\"]+)\"\s*;;", re.MULTILINE)
#: Упоминание файла шаблона в markdown (в т.ч. `diagrams/use-case.mmd`).
MMD_RE = re.compile(r"([a-z0-9-]+)\.mmd")


def _template_names() -> set[str]:
    """Имена всех `.mmd`-шаблонов (без расширения)."""
    return {path.stem for path in TEMPLATES.glob("*.mmd")}


def _scaffold_packs() -> dict[str, tuple[str, ...]]:
    """Паки из scaffold-run.sh: имя -> имена диаграмм без расширения."""
    text = SCAFFOLD.read_text(encoding="utf-8")
    packs: dict[str, tuple[str, ...]] = {}
    for name, files in PACK_CASE_RE.findall(text):
        packs[name] = tuple(file.removesuffix(".mmd") for file in files.split())
    return packs


def _mentioned_mmd(path: Path) -> set[str]:
    """Имена `.mmd`-файлов, упомянутых в markdown-файле."""
    return {name.removesuffix(".mmd") for name in MMD_RE.findall(path.read_text(encoding="utf-8"))}


def test_every_template_is_described_in_catalog() -> None:
    """Каждый `templates/*.mmd` описан в каталоге скила."""
    described = _mentioned_mmd(CATALOG_MD)

    missing = sorted(_template_names() - described)
    assert not missing, f"в diagram-catalog.md нет шаблонов: {missing}"


def test_catalog_has_no_ghost_templates() -> None:
    """Каталог не ссылается на несуществующие `.mmd`."""
    described = _mentioned_mmd(CATALOG_MD)

    ghosts = sorted(described - _template_names())
    assert not ghosts, f"в diagram-catalog.md упомянуты отсутствующие шаблоны: {ghosts}"


def test_scaffold_packs_match_check_dor() -> None:
    """`scaffold-run.sh` и `check_dor.PACK_DIAGRAMS` описывают один и тот же набор."""
    assert _scaffold_packs() == PACK_DIAGRAMS


def test_all_packs_declared_in_scaffold() -> None:
    """`ALL_PACKS` совпадает с ключами паков и порядком в check_dor."""
    text = SCAFFOLD.read_text(encoding="utf-8")
    match = ALL_PACKS_RE.search(text)

    assert match is not None, "в scaffold-run.sh нет ALL_PACKS"
    assert tuple(match.group(1).split()) == tuple(PACK_DIAGRAMS)


def test_start_prompt_mentions_packs_and_files() -> None:
    """start.md перечисляет паки и файлы, иначе check-sync их не увидит."""
    text = START_MD.read_text(encoding="utf-8")

    for pack in PACK_DIAGRAMS:
        assert f"{pack}:" in text, f"в prompts/start.md нет пака {pack}"
    for diagrams in PACK_DIAGRAMS.values():
        for name in diagrams:
            assert f"{name}.mmd" in text, f"в prompts/start.md нет {name}.mmd"


def test_handout_index_lists_every_template() -> None:
    """Раздатка знает про каждый шаблон: иначе владелец не назначен."""
    listed = _mentioned_mmd(HANDOUT)

    missing = sorted(_template_names() - listed)
    assert not missing, f"в handout-index.md нет диаграмм: {missing}"


def test_dor_profiles_only_use_known_diagrams() -> None:
    """Профили DoR не требуют диаграмм, которых нет в каталоге."""
    known = _template_names() | set(BASE_DIAGRAMS) | set(EXTENDED_DIAGRAMS)
    for pack in PACK_DIAGRAMS.values():
        known |= set(pack)

    unknown = sorted(known - _template_names())
    assert not unknown, f"профили ссылаются на отсутствующие шаблоны: {unknown}"
