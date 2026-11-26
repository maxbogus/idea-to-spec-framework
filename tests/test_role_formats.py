"""Контракты форматов ролей: поля, которые роль обещает в промпте.

Зачем. `auto-005` показал: Designer обязуется собирать CJM, но в формате
ответа поля `cjm` нет — модель возвращает свой обычный JSON, и CJM приходится
собирать отдельным запросом. Та же болезнь у System Analyst: текст промпта
ссылается на `assumptions`, а схема поля не объявляет.

Тесты статические: они читают промпты и проверяют, что обещанное поле
объявлено в JSON-блоке «Формат ответа».
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = REPO_ROOT / "prompts" / "roles"
SUBAGENTS_DIR = REPO_ROOT / "subagents"


def _format_block(path: Path) -> dict[str, Any]:
    """Извлечь JSON-блок «Формат ответа» из промпта роли."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"## Формат ответа.*?```json\n(.*?)```", text, re.DOTALL)
    assert match is not None, f"нет блока «Формат ответа» в {path}"
    return cast(dict[str, Any], json.loads(match.group(1)))


def test_designer_declares_cjm() -> None:
    """Designer объявляет блок cjm со stages — иначе CJM не собрать."""
    block = _format_block(ROLES_DIR / "designer.md")
    assert "cjm" in block
    assert "stages" in block["cjm"]
    assert "persona" in block["cjm"]


def test_system_analyst_declares_assumptions() -> None:
    """System Analyst объявляет assumptions, на которые ссылается текст."""
    block = _format_block(ROLES_DIR / "system-analyst.md")
    assert "assumptions" in block


def test_fact_check_declares_claim_and_artifact() -> None:
    """fact-check объявляет claim и artifact — иначе запись не связать с FR."""
    text = (SUBAGENTS_DIR / "fact-check.md").read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)```", text, re.DOTALL)
    assert match is not None
    schema = json.loads(match.group(1))
    finding = schema["outputs"]["findings"][0]
    assert {"claim", "artifact", "status", "source", "reason"} <= set(finding)
