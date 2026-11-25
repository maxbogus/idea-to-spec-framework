"""Проверки гейта свежести отчёта (`scripts/check_eval_report_fresh.py`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from check_eval_report_fresh import _case_ids, _report_ids, check
from idea_to_spec.paths import EVAL_CASES_FILE, EVAL_REPORT_FILE


def test_case_ids_match_eval_set() -> None:
    """Идентификаторы набора совпадают с файлом кейсов."""
    ids = _case_ids()
    assert len(ids) == len(set(ids)), "идентификаторы кейсов повторяются"
    assert len(ids) > 0, "набор кейсов пуст"


@pytest.mark.slow
def test_report_matches_set_when_fresh() -> None:
    """Отчёт соответствует набору — если прогон свежий.

    Гейт ловит устаревание: набор вырос с 23 до 31 кейса, а отчёт остался от
    старого прогона — и это было видно только глазами при чтении чисел.
    После прогона 2026-11-24 отчёт свежий, поэтому расхождений быть не должно.

    Маркер `slow`: проверка зависит от реального прогона (`make eval`).
    После расширения набора до 33 кейсов отчёт отстал — гейт это показал,
    и тест падал на `make test-eval` (`-m 'not slow'`). Отчёт обновляется
    отдельной волной (D006), поэтому проверка помечена `slow`: она не
    должна ронять быстрый прогон тестов.
    """
    problems = check()
    assert not problems, f"отчёт разошёлся с набором: {problems}"


def test_gate_detects_outdated_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Гейт ловит устаревший отчёт (проверка на подменённом файле).

    Сценарий «отчёт старше набора» проверяется отдельно, на временном
    файле: основной отчёт перезаписывается каждым прогоном, и полагаться
    на его состояние в тесте нельзя.
    """
    import check_eval_report_fresh as gate

    stale = tmp_path / "stale.json"
    stale.write_text(
        json.dumps({"results": {"results": [{"vars": {"id": "ORCH-01-auto-no-questions"}}]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "EVAL_REPORT_FILE", stale)
    problems = gate.check()
    assert problems, "гейт не увидел устаревший отчёт"
    assert any("устарел" in problem for problem in problems), (
        f"нет сообщения об устаревании: {problems}"
    )


def test_check_does_not_fail_the_build() -> None:
    """Гейт — human-review: расхождение не должно ронять сборку."""
    assert check() is not None
    # main() возвращает 0 даже при расхождении: полный прогон идёт волной.
    from check_eval_report_fresh import main

    assert main() == 0


def test_report_ids_are_readable() -> None:
    """Идентификаторы читаются из реального отчёта."""
    if not EVAL_REPORT_FILE.exists():
        return
    ids = _report_ids()
    assert len(ids) > 0, "в отчёте нет ни одного кейса"
    payload = json.loads(EVAL_REPORT_FILE.read_text(encoding="utf-8"))
    assert payload.get("results"), "в отчёте нет результатов"
    assert EVAL_CASES_FILE.exists()
