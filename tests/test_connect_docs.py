"""Контракт документа подключения: команды и пути не должны гнить."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "connect.md"
MAKEFILE = REPO_ROOT / "Makefile"
README = REPO_ROOT / "README.md"

#: Путь в backticks, который обязан существовать в репозитории.
PATH_RE = re.compile(r"`((?:prompts|skills|templates|scripts|docs|tests)/[^`\s]+)`")
#: `make <target>` без переменных и флагов (флаги вроде `-C` не матчатся).
MAKE_RE = re.compile(r"\bmake\s+([a-z][a-z0-9-]*)")


def test_connect_doc_exists() -> None:
    """Документ подключения существует."""

    assert DOC.is_file()


def test_connect_doc_mentions_entry_point() -> None:
    """Точка входа названа явно."""

    assert "prompts/start.md" in DOC.read_text(encoding="utf-8")


def test_documented_make_targets_exist() -> None:
    """Каждая `make <target>` из документа есть в Makefile."""

    text = DOC.read_text(encoding="utf-8")
    targets = set(MAKE_RE.findall(text))
    assert targets
    makefile = MAKEFILE.read_text(encoding="utf-8")
    missing = {
        target
        for target in targets
        if re.search(rf"^{re.escape(target)}:", makefile, re.MULTILINE) is None
    }
    assert not missing, f"нет целей в Makefile: {sorted(missing)}"


def test_documented_paths_exist() -> None:
    """Каждый repo-относительный путь из документа существует."""

    text = DOC.read_text(encoding="utf-8")
    missing = []
    for relative in PATH_RE.findall(text):
        if "<" in relative or "*" in relative or relative.startswith("framework/"):
            continue
        if not (REPO_ROOT / relative).exists():
            missing.append(relative)
    assert not missing, f"нет путей: {sorted(set(missing))}"


def test_readme_links_connect_doc() -> None:
    """README ведёт к документу подключения."""

    assert "docs/connect.md" in README.read_text(encoding="utf-8")
