"""Проверки ledger: измеренные факты и принятые решения.

Ledger (`prompts/ledger/*.jsonl`) — источник правды о том, что измерено, а
что решено. Проверки ниже не дают ему молча разъехаться: append-only
формат, уникальные идентификаторы, обязательные поля.

Формат проверяет и `scripts/check_ledger.py` (для Makefile-гейта) — здесь те
же правила, но с проверкой граничных случаев.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from check_ledger import REQUIRED_FIELDS, check_file

#: Каталог ledger.
LEDGER_DIR = Path(__file__).resolve().parent.parent / "prompts" / "ledger"

#: Имена файлов ledger по типу записи.
FILES = {"findings": "findings.jsonl", "decisions": "decisions.jsonl"}


@pytest.mark.parametrize("kind", sorted(FILES))
def test_ledger_file_exists(kind: str) -> None:
    """Файл ledger каждого типа существует."""
    assert (LEDGER_DIR / FILES[kind]).exists(), f"нет {FILES[kind]}"


@pytest.mark.parametrize("kind", sorted(FILES))
def test_ledger_format_valid(kind: str) -> None:
    """Формат ledger корректен (те же правила, что у check_ledger.py)."""
    problems = check_file(LEDGER_DIR / FILES[kind], kind)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("kind", sorted(FILES))
def test_ledger_ids_unique(kind: str) -> None:
    """Идентификаторы записей уникальны."""
    ids = [
        json.loads(line)["id"]
        for line in (LEDGER_DIR / FILES[kind]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(ids) == len(set(ids)), f"повторяющиеся id в {FILES[kind]}"


@pytest.mark.parametrize("kind", sorted(FILES))
def test_ledger_records_have_all_required_fields(kind: str) -> None:
    """У каждой записи есть все обязательные поля."""
    required = REQUIRED_FIELDS[kind]
    for number, line in enumerate(
        (LEDGER_DIR / FILES[kind]).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        for field in required:
            assert record.get(field), f"{FILES[kind]}:{number}: нет {field!r}"


def test_findings_have_evidence() -> None:
    """Каждая находка подкреплена измерением.

    Факт без измерения — не факт: находка без `evidence` не отличима от
    мнения, а ledger читается как источник истины.
    """
    for number, line in enumerate(
        (LEDGER_DIR / "findings.jsonl").read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        assert len(str(record.get("evidence"))) > 20, (
            f"findings.jsonl:{number}: evidence слишком короткое — "
            "находка без измерения"
        )
