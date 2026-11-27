"""Машинно-читаемые схемы ответов ролей (P4).

Зачем. До P4 единственным описанием формата был JSON-пример внутри
`prompts/roles/*.md`. Машина его не читала: `expected_fields` в eval-кейсах —
ручная копия схемы, и ничто не проверяло копию против источника. Дрейф
нашёлся сразу: PM-01 ждал поле `baseline`, PM-02 — `objections`, хотя это
вложенные поля (`success_metric.baseline`, `variants[].objections`), а не
поля верхнего уровня. Проверка `expected_fields` искала подстроку и дефекта
не видела.

Контракт: `prompts/schemas.yaml` — источник правды о верхнеуровневых полях
(имя, тип, обязательность, тип элементов массива). JSON-пример в промпте
обязан совпадать со схемой; `expected_fields` в eval — быть подмножеством
полей схемы; ответ модели проверяется структурно (`role_schema`).

Границы: вложенные формы (например, `outputs.findings[]`) остаются в
примерах промптов и `test_role_formats`; перекрёстные идентификаторы —
`check_cross_refs.py`. Схема P4 — про верхний уровень ответа.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from idea_to_spec.role_schemas import (
    ALLOWED_TYPES,
    FieldSpec,
    RoleSchema,
    case_contract_problems,
    check_all,
    check_prompt_matches_schema,
    load_schemas,
    validate_role_payload,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMAS = load_schemas(REPO_ROOT)


def _write_prompt(root: Path, body: str, name: str = "role.md") -> Path:
    """Записать промпт с блоком формата ответа."""
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def _schema(role: str = "test", fields: dict[str, FieldSpec] | None = None) -> RoleSchema:
    """Собрать схему для фикстуры."""
    return RoleSchema(
        role=role,
        prompt="role.md",
        fields=fields
        or {
            "personas": FieldSpec("personas", "array", items="object"),
            "open_questions": FieldSpec("open_questions", "array", items="string"),
        },
    )


def test_every_role_used_by_eval_has_a_schema() -> None:
    """У каждой роли из eval-набора есть запись в `prompts/schemas.yaml`."""
    cases = [
        json.loads(line)
        for line in (REPO_ROOT / "eval" / "cases" / "roles.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    roles = {json.loads(case["vars"]["contract"])["role"] for case in cases}
    assert roles <= set(SCHEMAS), f"без схемы: {sorted(roles - set(SCHEMAS))}"


def test_schema_definitions_are_valid() -> None:
    """Типы полей и элементов массивов — из допустимого набора."""
    for role, schema in SCHEMAS.items():
        assert schema.fields, f"{role}: пустая схема"
        for name, field in schema.fields.items():
            assert field.name == name, f"{role}.{name}: имя поля не совпадает с ключом"
            assert field.type in ALLOWED_TYPES, f"{role}.{name}: тип {field.type!r}"
            if field.items is not None:
                assert field.items in ALLOWED_TYPES, f"{role}.{name}: items {field.items!r}"


@pytest.mark.parametrize("role", sorted(SCHEMAS), ids=sorted(SCHEMAS))
def test_prompt_example_matches_schema(role: str) -> None:
    """JSON-пример в промпте совпадает со схемой по полям и типам."""
    problems = check_prompt_matches_schema(SCHEMAS[role], REPO_ROOT)
    assert not problems, "\n".join(problems)


def test_prompt_with_extra_field_is_reported(tmp_path: Path) -> None:
    """Поле, объявленное в промпте и отсутствующее в схеме, — дрейф."""
    _write_prompt(
        tmp_path,
        "# Роль\n\n## Формат ответа\n\n```json\n"
        '{"personas": [], "open_questions": [], "bonus": "x"}\n```\n',
    )
    problems = check_prompt_matches_schema(_schema(), tmp_path)
    assert any("bonus" in problem for problem in problems), problems


def test_prompt_with_missing_field_is_reported(tmp_path: Path) -> None:
    """Поле схемы, которого нет в примере промпта, — дрейф."""
    _write_prompt(
        tmp_path,
        "# Роль\n\n## Формат ответа\n\n```json\n"
        '{"personas": []}\n```\n',
    )
    problems = check_prompt_matches_schema(_schema(), tmp_path)
    assert any("open_questions" in problem for problem in problems), problems


def test_prompt_with_wrong_type_is_reported(tmp_path: Path) -> None:
    """Пример с другим типом поля — дрейф."""
    _write_prompt(
        tmp_path,
        "# Роль\n\n## Формат ответа\n\n```json\n"
        '{"personas": [], "open_questions": "вопрос"}\n```\n',
    )
    problems = check_prompt_matches_schema(_schema(), tmp_path)
    assert any("open_questions" in problem and "array" in problem for problem in problems), problems


def test_prompt_with_wrong_item_type_is_reported(tmp_path: Path) -> None:
    """Массив объектов там, где схема обещает массив строк, — дрейф."""
    _write_prompt(
        tmp_path,
        "# Роль\n\n## Формат ответа\n\n```json\n"
        '{"personas": [], "open_questions": [{"question": "x"}]}\n```\n',
    )
    problems = check_prompt_matches_schema(_schema(), tmp_path)
    assert any("open_questions" in problem and "string" in problem for problem in problems), problems


def test_case_expected_fields_must_be_top_level_fields() -> None:
    """`expected_fields` с вложенным полем — дефект контракта (реальный PM-01)."""
    problems = case_contract_problems(
        [
            {
                "id": "PM-X",
                "role": "product-manager",
                "expected_fields": ["success_metric", "baseline"],
            }
        ],
        SCHEMAS,
    )
    assert any("PM-X" in problem and "baseline" in problem for problem in problems), problems


def test_case_unknown_role_is_reported() -> None:
    """Кейс ссылается на роль без схемы — контракта нет."""
    problems = case_contract_problems(
        [{"id": "X-1", "role": "unknown-role", "expected_fields": []}],
        SCHEMAS,
    )
    assert any("unknown-role" in problem for problem in problems), problems


def test_real_eval_contracts_have_no_drift() -> None:
    """Все `expected_fields` реального набора — поля верхнего уровня схем."""
    assert check_all(REPO_ROOT) == []


def test_validate_payload_reports_missing_field() -> None:
    """Пропущенное обязательное поле — проблема."""
    problems = validate_role_payload("product-manager", {"problem_statement": "x"}, SCHEMAS)
    assert any("success_metric" in problem for problem in problems), problems


def test_validate_payload_reports_wrong_type() -> None:
    """Поле не того типа — проблема."""
    payload = {
        "problem_statement": "x",
        "success_metric": "быстро",
        "constraints": [],
        "risk_appetite": "low",
        "out_of_scope": [],
        "variants": [],
        "assumptions": [],
        "open_questions": [],
        "discovery": {},
    }
    problems = validate_role_payload("product-manager", payload, SCHEMAS)
    assert any("success_metric" in problem and "object" in problem for problem in problems), problems


def test_validate_payload_reports_wrong_item_type() -> None:
    """`open_questions` как массив объектов — проблема (измерено на SA-03)."""
    payload = {
        "problem_statement": "x",
        "success_metric": {},
        "constraints": [],
        "risk_appetite": "low",
        "out_of_scope": [],
        "variants": [],
        "assumptions": [],
        "open_questions": [{"question": "какой контур?"}],
        "discovery": {},
    }
    problems = validate_role_payload("product-manager", payload, SCHEMAS)
    assert any("open_questions" in problem for problem in problems), problems


def test_validate_payload_accepts_full_answer() -> None:
    """Полный ответ роли проходит проверку схемы."""
    payload = {
        "problem_statement": "x",
        "success_metric": {"name": "m", "target": "1", "baseline": "0"},
        "constraints": [],
        "risk_appetite": "low",
        "out_of_scope": [],
        "variants": [],
        "assumptions": [],
        "open_questions": [],
        "discovery": {},
    }
    assert validate_role_payload("product-manager", payload, SCHEMAS) == []


def test_validate_payload_unknown_role_is_reported() -> None:
    """Роль без схемы — проблема, а не молчаливый пропуск."""
    problems = validate_role_payload("no-such-role", {}, SCHEMAS)
    assert any("no-such-role" in problem for problem in problems), problems


def test_role_schema_semantic_check_is_wired() -> None:
    """`role_schema` доступен как структурная проверка eval-контракта."""
    from idea_to_spec.semantic_check import run_semantic_check

    output = json.dumps({"open_questions": [{"question": "x"}]}, ensure_ascii=False)
    problems = run_semantic_check("role_schema", output, "chat", role="product-manager")
    assert any("problem_statement" in problem for problem in problems), problems


def test_role_schema_semantic_check_is_inert_without_role() -> None:
    """Без роли проверка молчит: старые потребители не ломаются."""
    from idea_to_spec.semantic_check import run_semantic_check

    assert run_semantic_check("role_schema", "{}", "auto") == []


def test_every_role_prompt_has_a_schema() -> None:
    """Каждый промпт с JSON-форматом ответа покрыт схемой."""
    from idea_to_spec.role_schemas import _uncovered_prompts

    assert _uncovered_prompts(REPO_ROOT, SCHEMAS) == []
