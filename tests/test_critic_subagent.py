"""Контракт субагента-критика (P6): файл, конвейер, чек-лист, eval-кейс.

Зачем. Критик отвечает за то, чего не делает fact-check: противоречия,
пробелы, слабые критерии, додуманные числа. Если он не подключён к
конвейеру или не попал в чек-лист Spec-gate, роль существует только на
бумаге — а расхождения в требованиях остаются незамеченными.
"""

from __future__ import annotations

import json

from idea_to_spec.paths import PROMPTS_DIR, REPO_ROOT, SUBAGENTS_DIR

#: Промпт субагента-критика.
CRITIC_FILE = SUBAGENTS_DIR / "requirements-critic.md"
#: Промпт оркестратора — он запускает субагентов.
ORCHESTRATOR_FILE = PROMPTS_DIR / "orchestrator.md"
#: Стартовый промпт — таблица конвейера.
START_FILE = PROMPTS_DIR / "start.md"
#: Чек-листы гейтов — справочник оркестратора.
GATES_FILE = PROMPTS_DIR / "gate-checklists.md"
#: Единая таблица «роль → метод → скил → артефакт → гейт».
HANDOUT_FILE = REPO_ROOT / "handout-index.md"
#: Eval-набор.
CASES_FILE = REPO_ROOT / "eval" / "cases" / "roles.jsonl"

#: Статусы находок, которые критик обязан различать.
FINDING_STATUSES = ("противоречие", "пробел", "слабый AC", "додумано", "избыточная грануляция")


def test_critic_prompt_declares_findings_and_severity() -> None:
    """Промпт критика задаёт статусы находок, severity и вердикт."""
    text = CRITIC_FILE.read_text(encoding="utf-8")
    for status in FINDING_STATUSES:
        assert status in text, f"нет статуса находки: {status}"
    for field in ('"where"', '"why"', '"fix"', '"severity"', '"verdict"'):
        assert field in text, f"нет поля формата: {field}"
    assert "арбитр — человек" in text.lower()


def test_orchestrator_runs_critic_after_fact_check() -> None:
    """Оркестратор запускает критика перед Spec-gate — после fact-check."""
    text = ORCHESTRATOR_FILE.read_text(encoding="utf-8")
    assert "subagents/requirements-critic.md" in text
    assert text.index("subagents/fact-check.md") < text.index("subagents/requirements-critic.md")


def test_start_pipeline_includes_critic() -> None:
    """В таблице конвейера критik стоит на этапе Validation."""
    text = START_FILE.read_text(encoding="utf-8")
    assert "subagents/requirements-critic.md" in text
    validation_rows = [line for line in text.splitlines() if line.startswith("| Validation")]

    assert validation_rows, "в конвейере нет строки Validation"
    assert "requirements-critic" in validation_rows[0]


def test_handout_index_has_critic_row() -> None:
    """Единая таблица содержит строку роли критика."""
    text = HANDOUT_FILE.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if "requirements-critic.md" in line]
    assert rows, "нет строки критика в handout-index.md"
    assert "Spec-gate" in rows[0]


def test_spec_gate_checklist_requires_critic() -> None:
    """Чек-лист Spec-gate требует прогон критика и фиксацию расхождений."""
    text = GATES_FILE.read_text(encoding="utf-8")
    spec_gate = text.split("## Чеклист Spec-gate", 1)[1]
    assert "critic" in spec_gate.lower() or "критик" in spec_gate.lower()


def test_eval_case_for_critic_exists() -> None:
    """В наборе два кейса критика: надёжные находки и отдельно — пробел в покрытии."""
    contracts = [
        json.loads(json.loads(line)["vars"]["contract"])
        for line in CASES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    critic_cases = {case["id"]: case for case in contracts if case.get("scenario") == "CRIT"}
    assert len(critic_cases) == 2, f"ожидалось 2 кейса CRIT, получено {len(critic_cases)}"

    first = next(case for cid, case in critic_cases.items() if cid.startswith("CRIT-01"))
    assert first["role"] == "critic"
    joined = " ".join(first.get("must_contain", []))
    for marker in ("противоречие", "слабый", "додумано"):
        assert marker in joined, f"CRIT-01 не требует надёжную находку: {marker}"

    gap = next(case for cid, case in critic_cases.items() if cid.startswith("CRIT-02"))
    gap_markers = " ".join(gap.get("must_contain", []))
    assert "пробел" in gap_markers and "BR-2" in gap_markers


def test_critic_gap_case_is_a_recorded_model_failure() -> None:
    """Пробел в покрытии — измеренное ограничение 8B, а не тихо ослабленный кейс."""
    from test_eval_contract import KNOWN_MODEL_FAILURES

    assert "CRIT-02-detects-uncovered-business-requirement" in KNOWN_MODEL_FAILURES
