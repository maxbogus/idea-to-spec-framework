"""Аналитика прогона (P5): метрики в ответе оркестратора и в run-report.

Зачем. До P5 по артефактам прогона нельзя было ответить, сколько он стоил:
какая модель, сколько токенов, сколько было уточнений, какие скилы
применялись. `scripts/session_analytics.py` читает секцию «Метрики прогона»
из `run-report.md` и показывает её одной сводкой.

Числа не выдумываются: если метрика не измерена, в отчёте остаётся
прочерк, и сводка честно перечисляет незаполненные поля.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from session_analytics import (
    REQUIRED_METRICS,
    main,
    missing_metrics,
    parse_metrics,
    summarize_run,
)

from idea_to_spec.paths import PROMPTS_DIR, REPO_ROOT

#: Шаблон отчёта прогона — источник секции метрик.
TEMPLATE_FILE = REPO_ROOT / "templates" / "run-report.md"
#: Промпт оркестратора — владелец JSON-блока ответа.
ORCHESTRATOR_FILE = PROMPTS_DIR / "orchestrator.md"
#: JSON-блок формата ответа в промпте роли.
_JSON_BLOCK_RE = re.compile(r"```json\n(.*?)```", re.S)

#: Заполненный отчёт прогона.
FILLED_REPORT = """# Run Report — demo

## Вход

Идея.

## Метрики прогона

| Метрика | Значение | Источник |
|---|---|---|
| Модель | qwen3:8b | конфиг прогона |
| Версия промпта | ed57afc | git |
| Скилы | analyze-data.md, diagram-generation.md | handout-index |
| Токены (вход) | 1200 | Ollama usage |
| Токены (выход) | 800 | Ollama usage |
| Стоимость | 0 | локальная модель |
| Уточнения | 3 | open-questions.md |
| Длительность | 2520 | лог прогона |
| Успех | да | гейты |
"""

#: Отчёт старого формата — без секции метрик.
LEGACY_REPORT = """# Run Report — old

## Вход

Идея.

## Главный вывод прогона

Всё как раньше.
"""


def _write_report(tmp_path: Path, text: str) -> Path:
    """Создать прогон с заданным `run-report.md`."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "run-report.md").write_text(text, encoding="utf-8")
    return run


def test_parse_metrics_reads_table() -> None:
    """Метрики парсятся из таблицы в канонические имена полей."""
    metrics = parse_metrics(FILLED_REPORT)
    assert metrics["model"] == "qwen3:8b"
    assert metrics["tokens_in"] == "1200"
    assert metrics["clarifications"] == "3"
    assert metrics["success"] == "да"


def test_parse_metrics_ignores_legacy_report() -> None:
    """Отчёт без секции метрик даёт пустой словарь, а не исключение."""
    assert parse_metrics(LEGACY_REPORT) == {}


def test_summarize_run_reads_report_file(tmp_path: Path) -> None:
    """Сводка строится по файлу прогона."""
    run = _write_report(tmp_path, FILLED_REPORT)
    assert summarize_run(run)["prompt_version"] == "ed57afc"


def test_missing_metrics_lists_unfilled_fields() -> None:
    """Незаполненные обязательные метрики перечисляются явно."""
    metrics = parse_metrics(FILLED_REPORT)
    assert missing_metrics(metrics) == []
    assert "cost_usd" in missing_metrics({"model": "qwen3:8b"})


def test_main_reports_legacy_run_without_metrics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Старый прогон без метрик — не ошибка: скрипт объясняет, чего нет."""
    run = _write_report(tmp_path, LEGACY_REPORT)
    assert main(["session_analytics.py", str(run)]) == 0
    assert "метрик" in capsys.readouterr().out.lower()


def test_main_prints_metrics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Скрипт выводит значения метрик и предупреждает о незаполненных."""
    run = _write_report(tmp_path, FILLED_REPORT)
    assert main(["session_analytics.py", str(run)]) == 0
    out = capsys.readouterr().out
    assert "qwen3:8b" in out
    assert "2520" in out


def test_main_without_arguments_returns_usage_code() -> None:
    """Без аргументов — код 2 и подсказка по запуску."""
    assert main(["session_analytics.py"]) == 2


def test_template_contains_metrics_section() -> None:
    """Шаблон отчёта содержит секцию метрик со всеми обязательными полями."""
    text = TEMPLATE_FILE.read_text(encoding="utf-8")
    assert "## Метрики прогона" in text
    metrics = parse_metrics(text)
    assert set(REQUIRED_METRICS) <= set(metrics), sorted(set(REQUIRED_METRICS) - set(metrics))


def test_orchestrator_does_not_require_self_reported_metrics() -> None:
    """Метрики не входят в формат ответа оркестратора — это измеренное решение.

    F031: блок `metrics` (9 полей) в формате ответа стоил 5 ORCH-кейсов из 9
    на qwen3:8b — модель теряла хвост формата (`next`) и добивала ответ
    чужими полями (`privacy_by_design`, `integrations`) до обрыва по
    `num_predict`. Плюс модель не знает `tokens_in`/`cost_usd`, поэтому
    требование этих полей провоцирует выдуманные числа (D018).

    Тест — регрессионный сторож: если блок вернут в формат, сначала нужен
    замер `make eval-target FILTER="scenario=ORCH"`, а не «на глаз».
    """
    text = ORCHESTRATOR_FILE.read_text(encoding="utf-8")
    blocks = _JSON_BLOCK_RE.findall(text)
    assert blocks, "в промпте оркестратора нет JSON-блока формата ответа"
    schema = json.loads(blocks[0])
    assert "metrics" not in schema
