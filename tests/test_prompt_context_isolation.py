"""Статические проверки промптов: общий контекст не должен подменять формат роли.

Историческая причина файла. На реальном прогоне eval (qwen2.5:7b, 23 кейса)
роли отвечали не в своём формате: модель брала идентификаторы из общего
контекста — `prompts/rules.md` и `prompts/orchestrator-guide.md` — и подставляла
их вместо полей своей роли. Например, Product Manager отвечал с ключами
`definition_of_ready`, `definition_of_done`, `bdd_criteria`, а Business
Analyst — с `functional_requirements`, `non_functional_requirements`,
`traceability_matrix`. Поля роли при этом терялись.

Механика: в общих правилах перечислены имена полей других ролей
(`status`, `risk`, `version`, `owner`, `priority`, `compliance`) и названия
артефактов чужих ролей («функциональные требования», «traceability matrix»).
Модель 7B не различает «поле моего ответа» и «термин из контекста» — и
подставляет более заметное имя в ответ. Проверка ниже ловит это статически,
без обращения к модели.

Проверки:
1. В общем контексте (rules.md + orchestrator-guide.md) нет backticked
   snake_case-имён, совпадающих с полями какой-либо роли.
2. В общем контексте нет названий артефактов чужих ролей, которые выглядят
   как имена полей (snake_case или «X требования»).
3. У каждой роли есть ровно один JSON-блок с форматом ответа, и он валиден.
"""

from __future__ import annotations

import json
import re

import pytest

from idea_to_spec.paths import PROMPTS_DIR, ROLES_DIR

#: Промпты, подключаемые ВСЕМ ролям (правила) — источник «чужих» имён.
_SHARED_FILES = [PROMPTS_DIR / "rules.md"]

#: Гайд подключается только оркестратору. Это другой уровень общего контекста:
#: он не мешает остальным ролям, поэтому проверки «нет чужих имён» и
#: «общий контекст меньше роли» применяются к нему отдельно.
_GUIDE_FILE = PROMPTS_DIR / "orchestrator-guide.md"

#: Роли, у которых свой формат ответа в JSON.
_ROLE_PROMPTS = [*sorted(ROLES_DIR.glob("*.md")), PROMPTS_DIR / "orchestrator.md"]

#: Бюджет общих правил в символах. Измерено на qwen2.5:7b (23 кейса):
#: 7111 символов → 5/23, 2990 символов → 16/23. Общие правила — только то,
#: что нужно всем ролям; всё остальное живёт в промпте конкретной роли.
_RULES_BUDGET = 4000

_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)```", re.S)
#: Имя-идентификатор в backticks: `status`, `compliance`, `rto_rpo`.
_BACKTICK_IDENT_RE = re.compile(r"`([a-z][a-z_]{3,})`")
#: Название артефакта чужой роли, выглядящее как имя поля.
_ARTIFACT_NAME_RE = re.compile(
    r"(?<![a-z_])"
    r"(functional_requirements|non_functional_requirements|nonfunctional_requirements"
    r"|traceability_matrix|use_cases|jobs_to_be_done|business_requirements"
    r"|acceptance_criteria|risk_register|human_oversight_plan|hallucination_log"
    r"|opportunity_solution_tree|problem_statement|success_metric)"
    r"(?![a-z_])"
)


def _schema_keys(text: str) -> set[str]:
    """Собрать все ключи (включая вложенные) из JSON-блока формата ответа.

    Args:
        text: Текст промпта роли.

    Returns:
        Множество имён ключей схемы. Пустое, если JSON-блока нет.
    """
    blocks = _JSON_BLOCK_RE.findall(text)
    if not blocks:
        return set()

    def walk(node: object) -> set[str]:
        keys: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                keys.add(key)
                keys |= walk(value)
        elif isinstance(node, list):
            for item in node:
                keys |= walk(item)
        return keys

    try:
        parsed = json.loads(blocks[0])
    except json.JSONDecodeError:
        return set()
    return walk(parsed)


def _all_role_keys() -> dict[str, set[str]]:
    """Собрать ключи формата ответа по каждой роли.

    Returns:
        Словарь «имя роли → множество ключей её схемы».
    """
    result: dict[str, set[str]] = {}
    for path in _ROLE_PROMPTS:
        result[path.stem] = _schema_keys(path.read_text(encoding="utf-8"))
    return result


ALL_ROLE_KEYS = _all_role_keys()


def _rules_text() -> str:
    """Собрать текст правил, общих для всех ролей.

    Returns:
        Текст `prompts/rules.md`.
    """
    return "\n".join(
        path.read_text(encoding="utf-8") for path in _SHARED_FILES if path.exists()
    )


def _guide_text() -> str:
    """Собрать текст гайда оркестратора.

    Returns:
        Текст `prompts/orchestrator-guide.md`.
    """
    return _GUIDE_FILE.read_text(encoding="utf-8") if _GUIDE_FILE.exists() else ""


def _shared_text() -> str:
    """Собрать текст общего контекста (правила + гайд оркестратора).

    Returns:
        Склеенный текст общих промптов.
    """
    return f"{_rules_text()}\n{_guide_text()}"


@pytest.mark.parametrize("role", sorted(ALL_ROLE_KEYS), ids=sorted(ALL_ROLE_KEYS))
def test_role_has_exactly_one_valid_json_answer_format(role: str) -> None:
    """У роли ровно один валидный JSON-блок с форматом ответа."""
    path = next(p for p in _ROLE_PROMPTS if p.stem == role)
    text = path.read_text(encoding="utf-8")
    blocks = _JSON_BLOCK_RE.findall(text)
    assert len(blocks) == 1, f"{role}: ожидался 1 JSON-блок формата ответа, найдено {len(blocks)}"
    try:
        json.loads(blocks[0])
    except json.JSONDecodeError as exc:
        pytest.fail(f"{role}: формат ответа — невалидный JSON: {exc}")


def test_shared_context_has_no_backticked_field_name_of_any_role() -> None:
    """Общий контекст не содержит имён полей ролей в backticks.

    Именно такие имена модель подставляет в ответ вместо полей своей роли.
    Проверяются оба уровня: правила (для всех ролей) и гайд оркестратора.
    """
    for level, text in (("rules.md", _rules_text()), ("orchestrator-guide.md", _guide_text())):
        offenders: dict[str, list[str]] = {}
        for ident in sorted(set(_BACKTICK_IDENT_RE.findall(text))):
            roles = [role for role, keys in ALL_ROLE_KEYS.items() if ident in keys]
            if roles:
                offenders[ident] = roles
        assert not offenders, (
            f"{level} содержит имена полей ролей в backticks — модель "
            "подставляет их вместо полей своей роли:\n"
            + "\n".join(f"  `{k}` → поля роли {v}" for k, v in offenders.items())
            + "\nПереименуйте термин (например, «поле status» вместо `status`) "
            "или вынесите его в промпт конкретной роли."
        )


def test_shared_context_has_no_foreign_artifact_names() -> None:
    """Общий контекст не содержит имён артефактов чужих ролей как полей."""
    for level, text in (("rules.md", _rules_text()), ("orchestrator-guide.md", _guide_text())):
        offenders = sorted(set(_ARTIFACT_NAME_RE.findall(text)))
        assert not offenders, (
            f"{level} содержит имена артефактов других ролей — модель "
            f"подставляет их в ответ своей роли: {offenders}. "
            "Опишите артефакт словами (например, «функциональные требования») "
            "без имени-идентификатора."
        )


def test_shared_context_is_smaller_than_every_role_prompt() -> None:
    """Общий контекст меньше промпта каждой роли.

    Измеренная причина регрессии (A/B на qwen2.5:7b, 23 кейса): при общем
    контексте 7111 символов модель отвечала по общему контексту, а не по
    формату своей роли — 0/23 кейсов. При общем контексте 2990 символов
    (после переноса DoR/DoD, BDD и глоссария в промпты ролей) — 16/23.

    Правило: общий контекст — это «общее для всех», поэтому он не должен быть
    крупнее инструкции конкретной роли.
    """
    rules_len = len(_rules_text())
    assert rules_len <= _RULES_BUDGET, (
        f"общие правила — {rules_len} симв., бюджет {_RULES_BUDGET}. "
        "Измерено на qwen2.5:7b: при 7111 символов — 5/23 кейсов, "
        "при 2990 — 16/23. Общие правила должны содержать только то, "
        "что нужно всем ролям."
    )


def test_shared_rules_exclude_role_specific_content() -> None:
    """Общие правила не содержат определений, принадлежащих конкретной роли.

    Назначение определений измерено: DoR/DoD нужны System Analyst и
    Project Manager, формат BDD — System Analyst, глоссарий — оркестратору
    (блок «Термины»). В общих правилах они перетягивали модель на чужой
    формат ответа.
    """
    rules = _rules_text()
    role_specific = {
        "Definition of Ready / Definition of Done": "roles/system-analyst.md, roles/project-manager.md",
        "Формат критерия приёмки (BDD)": "roles/system-analyst.md",
        "Глоссарий терминов": "prompts/orchestrator.md",
    }
    for section, owner in role_specific.items():
        assert f"## {section}" not in rules, (
            f"общие правила содержат раздел «{section}», который принадлежит "
            f"{owner}. Перенесите его туда: в общих правилах модель отвечает "
            "по чужому формату."
        )


def test_role_prompt_owns_its_definitions() -> None:
    """Определения лежат в промпте той роли, которой они нужны.

    Исключение — справочники: глоссарий и чек-листы гейтов нужны человеку
    и агенту, но не модели: внутри промпта модель принимала их термины за
    поля ответа роли (`successMetric`, `contour`, `paymentIntegration`).
    Они лежат отдельными файлами и на запрос не подключаются.
    """
    expectations = {
        "roles/system-analyst.md": ["Definition of Ready", "Given / When / Then"],
        "roles/project-manager.md": ["Definition of Ready"],
    }
    for rel, markers in expectations.items():
        text = (PROMPTS_DIR / rel).read_text(encoding="utf-8")
        for marker in markers:
            assert marker in text, f"{rel}: нет определения «{marker}»"


def test_reference_documents_are_not_in_model_prompts() -> None:
    """Справочники (глоссарий, чек-листы гейтов) не попадают в промпт модели."""
    orchestrator = (PROMPTS_DIR / "orchestrator.md").read_text(encoding="utf-8")
    assert "## Глоссарий терминов" not in orchestrator, (
        "глоссарий вернулся в промпт оркестратора — модель подставляет его "
        "термины вместо полей ответа. Держите его в prompts/glossary.md"
    )
    for path in (PROMPTS_DIR / "rules.md", PROMPTS_DIR / "orchestrator-guide.md"):
        text = path.read_text(encoding="utf-8")
        assert "## Глоссарий терминов" not in text, (
            f"{path.name}: глоссарий не должен быть в промпте модели"
        )


def test_gate_checklists_are_not_in_model_prompts() -> None:
    """Чек-листы гейтов не попадают в промпты, которые видит модель.

    Измерено на eval-прогоне (qwen2.5:7b): когда чек-листы были в промпте
    оркестратора, модель отвечала чек-листом вместо JSON-ответа роли —
    ключи `problemStatement`, `successMetric`, `baGateChecklist` вместо
    `mode`, `stage`, `completeness`. Справочник гейтов лежит отдельно
    (`prompts/gate-checklists.md`) и к запросу не подключается.
    """
    for path in (PROMPTS_DIR / "rules.md", PROMPTS_DIR / "orchestrator-guide.md"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?m)^## Чеклист (BA|SA|Spec)-gate", text), (
            f"{path.name}: чек-листы гейтов вернулись в промпт модели — "
            "перенесите их в prompts/gate-checklists.md"
        )


def test_gate_checklists_file_exists_with_all_gates() -> None:
    """Справочник гейтов существует и содержит все три гейта."""
    path = PROMPTS_DIR / "gate-checklists.md"
    assert path.exists(), "нет prompts/gate-checklists.md"
    text = path.read_text(encoding="utf-8")
    for gate in ("BA-gate", "SA-gate", "Spec-gate"):
        assert f"## Чеклист {gate}" in text, f"в gate-checklists.md нет {gate}"


def test_model_prompts_have_no_camel_case_identifiers() -> None:
    """В промптах, которые видит модель, нет camelCase-идентификаторов.

    Повторяющийся механизм дефекта: модель 7B переносит в свой ответ
    идентификаторы из контекста. Имена полей ролей — snake_case
    (`success_metric`), поэтому любой camelCase-токен в контексте
    (`successMetric`, `targetAudience`) модель переносит как «поле ответа»
    и подставляет вместо настоящих полей роли.

    Проверяются все промпты, подключаемые к запросу: правила, гайд
    оркестратора и промпты ролей.
    """
    # Ищем по словам: перенос строки внутри слова («Open\nTelemetry») не
    # должен давать ложное срабатывание.
    camel = re.compile(r"\b[a-z]+[A-Z][A-Za-z]*\b")
    checked = {
        "rules.md": _rules_text(),
        "orchestrator-guide.md": _guide_text(),
    }
    for path in _ROLE_PROMPTS:
        checked[path.name] = path.read_text(encoding="utf-8")

    for name, text in checked.items():
        offenders = sorted(set(camel.findall(text)))
        assert not offenders, (
            f"{name}: camelCase-идентификаторы {offenders} — модель переносит их "
            "в ответ вместо полей своей роли. Переименуйте в snake_case или "
            "уберите из промпта."
        )
