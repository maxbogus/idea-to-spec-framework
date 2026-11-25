"""Проверки согласованности идентификаторов в схемах ролей.

Регрессия `BA-01-personas-jtbd`: в схеме ответа `personas` были объявлены
массивом строк, а `jobs_to_be_done[].persona` ожидал идентификатор персоны.
Модель писала имя («Студент») вместо `P-1` — ей не выдали идентификатор,
который потом требовали. Кейс падал у `qwen3:8b` и проходил у
`qwen2.5:7b`: разница была в формулировке, а не в модели.

Валидатор превращает этот класс дефектов в гейт: `check_cross_refs.py`
(семантический аналог `check-refs`, который проверяет существование файлов).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from check_cross_refs import check_role

#: Каталог промптов ролей.
ROLES_DIR = Path(__file__).resolve().parent.parent / "prompts" / "roles"


@pytest.mark.parametrize("path", sorted(ROLES_DIR.glob("*.md")), ids=lambda p: p.stem)
def test_role_cross_references_consistent(path: Path) -> None:
    """В схеме каждой роли идентификаторы согласованы между собой."""
    problems = check_role(path)
    assert not problems, "\n".join(problems)


def test_personas_must_declare_id_when_jtbd_references_it() -> None:
    """Проверка ловит рассинхрон: ссылка на персону без объявления id."""
    broken = """# Роль: Тест

## Формат ответа

```json
{
  "personas": ["кто пользователь"],
  "jobs_to_be_done": [{"id": "J-1", "persona": "P-1"}]
}
```
"""
    path = Path("/tmp/_broken_role.md")
    path.write_text(broken, encoding="utf-8")
    try:
        problems = check_role(path)
    finally:
        path.unlink(missing_ok=True)
    assert problems, "рассинхрон persona должен быть найден"
    assert "persona" in problems[0]


def test_task_depends_on_requires_declared_ids() -> None:
    """Проверка ловит рассинхрон: depends_on без id у задач."""
    broken = """# Роль: Тест

## Формат ответа

```json
{
  "tasks": [{"title": "...", "depends_on": ["T-1"]}]
}
```
"""
    path = Path("/tmp/_broken_tasks.md")
    path.write_text(broken, encoding="utf-8")
    try:
        problems = check_role(path)
    finally:
        path.unlink(missing_ok=True)
    assert problems, "ссылка depends_on без id должна быть найдена"


def test_consistent_role_passes() -> None:
    """Согласованная схема проходит проверку."""
    good = """# Роль: Тест

## Формат ответа

```json
{
  "personas": [{"id": "P-1", "name": "Клиент"}],
  "jobs_to_be_done": [{"id": "J-1", "persona": "P-1"}]
}
```
"""
    path = Path("/tmp/_good_role.md")
    path.write_text(good, encoding="utf-8")
    try:
        problems = check_role(path)
    finally:
        path.unlink(missing_ok=True)
    assert not problems


def test_business_analyst_personas_declare_id() -> None:
    """В схеме Business Analyst персоны объявляют id — как в эталоне."""
    path = ROLES_DIR / "business-analyst.md"
    schema = json.loads(
        path.read_text(encoding="utf-8").split("```json")[1].split("```")[0]
    )
    assert "id" in schema["personas"][0], (
        "personas должны объявлять id: jobs_to_be_done[].persona ссылается на него"
    )
