"""Контракт гейта: чеклист, `checks[]`, валидатор и подключение к прогону.

Зачем. Дефект волны C — «гейт-печать»: BA-gate сказал `passed` при четырёх
незакрытых пунктах, и это было видно только глазами. Причина не в модели, а в
контракте: у вердикта не было адресуемых пунктов. Тесты фиксируют:

- чеклист — машинно-читаемый источник (`prompts/gate-checklists.yaml`), а
  человеческий справочник — производная от него (как `skills/INDEX.md`);
- отдельный вызов гейта получает чеклист с id во входе, но не содержит его в
  промпте (иначе модель принимает чеклист за формат ответа — измерено);
- ответ гейта проверяется одинаково в eval, в прогоне и руками: полнота
  `checks`, согласованность `status`/`missing`/`return_to`, `na` только для
  условных пунктов.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from check_gate import check_file

from check_run import check_run
from idea_to_spec.gate_checklists import (
    check_markdown,
    extract_gate_payloads,
    gate_spec,
    load_gates,
    render_gate_input,
    validate_gate_payload,
)
from idea_to_spec.paths import EVAL_CASES_FILE, PROMPTS_DIR, REPO_ROOT

#: Пункты, для которых `na` — легальный вердикт: они условны по входу.
NA_ALLOWED = {
    "BA-07",
    "SA-07",
    "SA-11",
    "SA-12",
    "SA-13",
    "SA-14",
    "SA-15",
    "SP-08",
}

#: Этапы из enum оркестратора: `return_to` и `stage` — только из него.
STAGES = {
    "intake",
    "business",
    "ba_gate",
    "design_sketch",
    "system",
    "sa_gate",
    "architecture",
    "validation",
    "spec_gate",
    "plan",
    "design_cjm",
    "done",
}


def _payload(
    gate: str,
    fails: tuple[str, ...] = (),
    nas: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Собрать валидный ответ гейта по чеклисту.

    Args:
        gate: Имя гейта.
        fails: Пункты со статусом `fail`.
        nas: Пункты со статусом `na` (только условные).

    Returns:
        Ответ гейта.
    """
    spec = gate_spec(gate)
    checks: list[dict[str, str]] = []
    for item in spec.items:
        if item.id in fails:
            checks.append({"id": item.id, "status": "fail", "evidence": "в артефактах нет"})
        elif item.id in nas:
            checks.append(
                {
                    "id": item.id,
                    "status": "na",
                    "reason": "пункт к этому входу не применим",
                    "evidence": "",
                }
            )
        else:
            checks.append({"id": item.id, "status": "pass", "evidence": "подтверждено"})
    missing = sorted(fails)
    return {
        "gate": gate,
        "status": "failed" if missing else "passed",
        "checks": checks,
        "missing": missing,
        "return_to": spec.return_to[0] if missing else "",
    }


def _problems(payload: dict[str, Any]) -> list[str]:
    """Проверить ответ гейта ожидаемым именем из самого ответа."""
    return validate_gate_payload(payload, str(payload.get("gate") or ""))


def test_yaml_declares_three_gates_with_unique_ids() -> None:
    """В YAML три гейта, id уникальны, префикс id совпадает с гейтом."""
    gates = load_gates(REPO_ROOT)
    assert list(gates) == ["BA-gate", "SA-gate", "Spec-gate"]

    all_ids: list[str] = []
    prefixes = {"BA-gate": "BA-", "SA-gate": "SA-", "Spec-gate": "SP-"}
    for name, spec in gates.items():
        assert spec.items, f"{name}: пустой чеклист"
        for item in spec.items:
            assert item.id.startswith(prefixes[name]), f"{name}: чужой префикс у {item.id}"
            assert item.text.strip(), f"{item.id}: пустая формулировка"
            all_ids.append(item.id)
    assert len(all_ids) == len(set(all_ids)), "id пунктов повторяются между гейтами"


def test_yaml_marks_only_conditional_items_as_na_allowed() -> None:
    """`na_allowed` стоит ровно на условных пунктах, остальные обязательны."""
    items = {item.id: item for spec in load_gates(REPO_ROOT).values() for item in spec.items}
    assert {item_id for item_id, item in items.items() if item.na_allowed} == NA_ALLOWED


def test_yaml_return_to_uses_orchestrator_stages() -> None:
    """`return_to` состоит из этапов enum оркестратора, а не из фантазий."""
    for spec in load_gates(REPO_ROOT).values():
        assert spec.return_to, f"{spec.name}: пустой return_to"
        unknown = set(spec.return_to) - STAGES
        assert not unknown, f"{spec.name}: неизвестные этапы {sorted(unknown)}"
        assert spec.stage in STAGES, f"{spec.name}: неизвестный stage {spec.stage!r}"


def test_markdown_is_generated_from_yaml() -> None:
    """Справочник соответствует YAML и содержит каждый id."""
    assert check_markdown(REPO_ROOT) == []
    text = (PROMPTS_DIR / "gate-checklists.md").read_text(encoding="utf-8")
    for spec in load_gates(REPO_ROOT).values():
        assert f"## Чеклист {spec.name}" in text
        for item in spec.items:
            assert f"`{item.id}`" in text, f"{item.id}: нет в справочнике"


def test_security_subsection_survives_render() -> None:
    """Подраздел чек-листа безопасности не теряется при рендере."""
    text = (PROMPTS_DIR / "gate-checklists.md").read_text(encoding="utf-8")
    assert "### Чек-лист безопасности (для high-risk доменов)" in text
    assert "`SA-12`" in text


def test_gate_prompt_declares_machine_readable_verdict() -> None:
    """Промпт гейта объявляет поля checks/status/missing/return_to.

    Чеклист в промпт не переносится: он приходит во входе вызова. В формате
    ответа допустимы только id из примера — если в промпте появился весь
    чеклист, модель начнёт отвечать им, а не вердиктом (измеренный механизм).
    """
    text = (PROMPTS_DIR / "roles" / "gate-reviewer.md").read_text(encoding="utf-8")
    for field in ('"gate"', '"status"', '"checks"', '"id"', '"evidence"', '"reason"'):
        assert field in text, f"нет поля формата: {field}"
    assert '"missing"' in text and '"return_to"' in text
    assert "ЧЕКЛИСТ" in text, "промпт не объясняет, откуда берётся чеклист"

    example_ids = {"BA-01", "BA-04", "BA-07"}
    leaked = [
        item.id
        for item in gate_spec("BA-gate").items
        if item.id not in example_ids and item.id in text
    ]
    assert not leaked, f"чеклист попал в промпт гейта: {leaked}"


def test_gate_input_contains_every_item_and_na_marker() -> None:
    """Вход гейта содержит каждый id и пометку «допустим na» для условных."""
    for spec in load_gates(REPO_ROOT).values():
        block = render_gate_input(spec.name, REPO_ROOT)
        assert f"ГЕЙТ: {spec.name}" in block
        assert "КУДА ВОЗВРАЩАТЬ: " + ", ".join(spec.return_to) in block
        for item in spec.items:
            line = f"- {item.id} — {item.text}"
            assert line in block
            if item.na_allowed:
                assert f"{line} [допустим na]" in block


@pytest.mark.parametrize(
    "gate,fails,nas",
    [
        ("BA-gate", (), ()),
        ("BA-gate", (), ("BA-07",)),
        ("SA-gate", ("SA-09", "SA-10"), ()),
        ("SA-gate", ("SA-02",), ("SA-07", "SA-12")),
        ("Spec-gate", (), ("SP-08",)),
        ("Spec-gate", ("SP-09",), ()),
    ],
)
def test_valid_payloads_pass(gate: str, fails: tuple[str, ...], nas: tuple[str, ...]) -> None:
    """Согласованный ответ гейта проходит проверку без замечаний."""
    assert _problems(_payload(gate, fails, nas)) == []


def test_payload_without_checks_is_rejected() -> None:
    """Пустой `checks` — не вердикт: гейт обязан ответить по каждому пункту."""
    payload = _payload("BA-gate")
    payload["checks"] = []
    assert any("checks пуст" in problem for problem in _problems(payload))


def test_dropped_item_is_rejected() -> None:
    """Пропущенный пункт чеклиста — проблема: молчаливый пропуск и есть дефект."""
    payload = _payload("BA-gate")
    payload["checks"] = payload["checks"][1:]
    assert any("BA-01" in problem for problem in _problems(payload))


def test_unknown_item_is_rejected() -> None:
    """Пункт не из чеклиста — проблема: чеклист нельзя расширять на ходу."""
    payload = _payload("BA-gate")
    payload["checks"].append({"id": "BA-99", "status": "pass", "evidence": "x"})
    assert any("BA-99" in problem for problem in _problems(payload))


def test_duplicate_item_is_rejected() -> None:
    """Повтор пункта — проблема: один пункт, один вердикт."""
    payload = _payload("BA-gate")
    payload["checks"].append(copy.deepcopy(payload["checks"][0]))
    assert any("повторяется" in problem for problem in _problems(payload))


def test_na_on_required_item_is_rejected() -> None:
    """`na` на обязательном пункте — проблема: это способ обойти проверку."""
    payload = _payload("BA-gate")
    payload["checks"][0] = {
        "id": "BA-01",
        "status": "na",
        "reason": "не хотелось проверять",
        "evidence": "",
    }
    assert any("BA-01: пункт не допускает na" in problem for problem in _problems(payload))


def test_na_without_reason_is_rejected() -> None:
    """`na` без причины — проблема: необъяснимый пропуск неотличим от пропуска."""
    payload = _payload("BA-gate", nas=("BA-07",))
    payload["checks"][6]["reason"] = ""
    assert any("BA-07: na без причины" in problem for problem in _problems(payload))


def test_pass_without_evidence_is_rejected() -> None:
    """`pass` без доказательства — проблема: это и есть гейт-печать."""
    payload = _payload("BA-gate")
    payload["checks"][0]["evidence"] = ""
    assert any("BA-01: статус pass без evidence" in problem for problem in _problems(payload))


def test_missing_must_match_failed_items() -> None:
    """`missing` — производная от `fail`; расхождение ломает адресацию."""
    payload = _payload("SA-gate", fails=("SA-09",))
    payload["missing"] = []
    assert any("missing не совпадает" in problem for problem in _problems(payload))


def test_passed_with_fail_is_rejected() -> None:
    """`passed` при проваленном пункте — гейт-печать, а не прохождение."""
    payload = _payload("SA-gate", fails=("SA-09",))
    payload["status"] = "passed"
    assert any("status=passed" in problem for problem in _problems(payload))


def test_failed_without_fail_is_rejected() -> None:
    """`failed` без проваленного пункта — вердикт без адреса."""
    payload = _payload("BA-gate")
    payload["status"] = "failed"
    assert any("status=failed" in problem for problem in _problems(payload))


def test_failed_requires_return_to() -> None:
    """Провал без `return_to` — проблема: неполнота без адресата не гейт."""
    payload = _payload("SA-gate", fails=("SA-09",))
    payload["return_to"] = ""
    assert any("failed без return_to" in problem for problem in _problems(payload))


def test_return_to_outside_gate_is_rejected() -> None:
    """Возврат на чужой этап — проблема: гейт знает только свои адреса."""
    payload = _payload("BA-gate", fails=("BA-04",))
    payload["return_to"] = "architecture"
    assert any("return_to" in problem for problem in _problems(payload))


def test_unknown_gate_and_non_object_are_rejected() -> None:
    """Неизвестный гейт и не-объект отклоняются без исключений."""
    assert validate_gate_payload({"gate": "UX-gate", "status": "passed"})
    assert validate_gate_payload(["не объект"]) == ["ответ гейта — не JSON-объект"]


def test_expected_gate_mismatch_is_reported() -> None:
    """Ответ не того гейта — проблема: кейс проверяет конкретный гейт."""
    payload = _payload("BA-gate")
    problems = validate_gate_payload(payload, "SA-gate")
    assert any("не совпадает с ожидаемым" in problem for problem in problems)



def _gate_cases() -> list[dict[str, Any]]:
    """Вернуть контракты GATE-кейсов из eval-набора."""
    cases: list[dict[str, Any]] = []
    for line in EVAL_CASES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        contract = json.loads(json.loads(line)["vars"]["contract"])
        if contract.get("scenario") == "GATE":
            cases.append(contract)
    return cases


def test_eval_cases_cover_gates_and_reference_checklist() -> None:
    """В наборе три GATE-кейса; их id провалов и na существуют в чеклисте."""
    cases = _gate_cases()
    assert [case["id"] for case in cases] == [
        "GATE-01-ba-gate-passed",
        "GATE-02-sa-gate-failed-return",
        "GATE-03-spec-gate-na-allowed",
    ]
    for case in cases:
        assert case["role"] == "gate-reviewer"
        assert "gate_contract" in case["semantic_checks"]
        spec = gate_spec(str(case["gate"]))
        for item_id in [*case["expected_fail_ids"], *case["expected_na_ids"]]:
            assert spec.item(item_id) is not None, f"{case['id']}: {item_id} нет в чеклисте"


@pytest.mark.mock
def test_mock_answers_for_gate_cases_pass_contract() -> None:
    """Mock-ответы гейтов проходят тот же валидатор, что и реальный прогон."""
    from mock_provider import build_answer

    for case in _gate_cases():
        payload = json.loads(build_answer(dict(case)))
        assert validate_gate_payload(payload, str(case["gate"])) == [], case["id"]


def test_transform_feeds_checklist_to_gate_call() -> None:
    """Transform подставляет чеклист в вход отдельного вызова гейта."""
    from promptfoo_transform import transform_vars

    case = _gate_cases()[1]
    merged = transform_vars(
        {"id": case["id"], "contract": json.dumps(case, ensure_ascii=False)}
    )
    text = str(merged["input"])
    assert text.startswith("ГЕЙТ: SA-gate")
    assert "SA-15" in text, "условный пункт безопасности не доехал до гейта"
    assert text.index("ЧЕКЛИСТ") < text.index("АРТЕФАКТЫ")
    assert str(case["input"]) in text, "артефакты кейса потерялись"


def test_transform_requires_gate_for_gate_role() -> None:
    """Кейс гейта без поля gate падает громко, а не идёт с пустым чеклистом."""
    from promptfoo_transform import transform_vars

    contract = {"id": "GATE-X", "role": "gate-reviewer", "input": "артефакты"}
    with pytest.raises(ValueError, match="требует поля gate"):
        transform_vars({"id": "GATE-X", "contract": json.dumps(contract)})


def test_transform_keeps_other_roles_input_unchanged() -> None:
    """Для остальных ролей вход не меняется: их промпты не удлиняются."""
    from promptfoo_transform import transform_vars

    contract = {"id": "ORCH-01", "role": "orchestrator", "input": "идея", "mode": "auto"}
    merged = transform_vars({"id": "ORCH-01", "contract": json.dumps(contract)})
    assert merged["input"] == "идея"



def _run_with_report(tmp_path: Path, report: str) -> list[str]:
    """Создать прогон с одним validation-report.md и проверить его."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "validation-report.md").write_text(report, encoding="utf-8")
    return check_run(run)


def _gate_section(payload: dict[str, Any]) -> str:
    """Обернуть ответ гейта в markdown-раздел «Гейты»."""
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"# Validation Report\n\n## Гейты\n\n```json\n{body}\n```\n"


def test_check_run_accepts_valid_gate_section(tmp_path: Path) -> None:
    """Согласованный раздел «Гейты» прогон не ломает."""
    problems = _run_with_report(tmp_path, _gate_section(_payload("BA-gate", fails=("BA-04",))))
    assert not any("validation-report" in problem for problem in problems), problems


def test_check_run_reports_gate_forgery(tmp_path: Path) -> None:
    """Гейт-печать в прогоне ловится: passed при проваленном пункте."""
    payload = _payload("BA-gate")
    payload["checks"][0]["status"] = "fail"
    payload["missing"] = ["BA-01"]
    payload["return_to"] = "business"
    problems = _run_with_report(tmp_path, _gate_section(payload))
    assert any("status=passed" in problem for problem in problems), problems


def test_check_run_reports_broken_gate_json(tmp_path: Path) -> None:
    """Битый JSON в разделе «Гейты» — проблема, а не тихий пропуск."""
    report = "# Validation Report\n\n## Гейты\n\n```json\n{\"gate\": \"BA-gate\",\n```\n"
    problems = _run_with_report(tmp_path, report)
    assert any("невалидный JSON" in problem for problem in problems), problems


def test_check_run_skips_old_runs_without_gate_section(tmp_path: Path) -> None:
    """Старый прогон без раздела «Гейты» принимается: проверка условна."""
    problems = _run_with_report(tmp_path, "# Validation Report\n\n## Итог\n")
    assert not any("validation-report" in problem for problem in problems), problems


def test_extract_gate_payloads_ignores_other_sections() -> None:
    """JSON-блоки вне раздела «Гейты» не считаются вердиктом гейта."""
    payloads, problems = extract_gate_payloads('# X\n\n```json\n{"a": 1}\n```\n')
    assert payloads == []
    assert problems == []
    assert extract_gate_payloads("## Гейты\n\nпусто\n") == ([], [])


def test_check_gate_cli_accepts_json_and_markdown(tmp_path: Path) -> None:
    """CLI проверяет и JSON-файл, и markdown-отчёт с разделом «Гейты»."""
    good = tmp_path / "gate.json"
    good.write_text(json.dumps(_payload("BA-gate")), encoding="utf-8")
    assert check_file(good) == []

    report = tmp_path / "validation-report.md"
    report.write_text(_gate_section(_payload("Spec-gate", nas=("SP-08",))), encoding="utf-8")
    assert check_file(report, "Spec-gate") == []


def test_check_gate_cli_reports_bad_files(tmp_path: Path) -> None:
    """CLI возвращает проблемы на битом JSON, пустом отчёте и отсутствии файла."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"gate": "BA-gate"}), encoding="utf-8")
    assert check_file(bad)

    empty = tmp_path / "empty.md"
    empty.write_text("# Validation Report\n", encoding="utf-8")
    assert check_file(empty)

    assert check_file(tmp_path / "missing.json")

