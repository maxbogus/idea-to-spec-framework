"""Проверки лёгкого guardrail для артефактов (P2).

Скрипт не роняет гейт: находки — предупреждения, требующие human-review.
Проверяем именно это: находки находятся, а код возврата остаётся 0.
"""

from __future__ import annotations

from pathlib import Path

from check_artifact_policy import check_policy, main


def _run_with(tmp_path: Path, content: str) -> Path:
    """Создать прогон с одним артефактом и вернуть путь к нему."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "brief.md").write_text(content, encoding="utf-8")
    return run


def test_clean_artifact_has_no_warnings(tmp_path: Path) -> None:
    """Обычный текст спецификации не даёт находок."""
    run = _run_with(
        tmp_path,
        "# Краткое описание\n\nПользователь создаёт заметку за ≤ 30 секунд.\n",
    )
    assert check_policy(run) == []


def test_email_is_flagged(tmp_path: Path) -> None:
    """Email-адрес помечается как требующий human-review."""
    run = _run_with(tmp_path, "Контакт: ivan.petrov@example.com\n")
    warnings = check_policy(run)
    assert any("email" in w for w in warnings)


def test_phone_is_flagged(tmp_path: Path) -> None:
    """Номер телефона помечается как требующий human-review."""
    run = _run_with(tmp_path, "Телефон поддержки: +7 916 237-45-00\n")
    warnings = check_policy(run)
    assert any("телефон" in w for w in warnings)


def test_secret_assignment_is_flagged(tmp_path: Path) -> None:
    """Присвоенный ключ помечается как требующий human-review."""
    run = _run_with(tmp_path, "api_key = example-not-a-real-key\n")
    warnings = check_policy(run)
    assert any("секрет" in w for w in warnings)


def test_missing_run_dir_is_reported(tmp_path: Path) -> None:
    """Несуществующий каталог — находка, а не тихий успех."""
    assert check_policy(tmp_path / "missing")


def test_main_returns_zero_even_with_findings(tmp_path: Path) -> None:
    """Находки не роняют гейт: решение принимает человек."""
    run = _run_with(tmp_path, "Контакт: ivan@example.com\n")
    assert main(["check_artifact_policy.py", str(run)]) == 0


def test_main_returns_zero_on_clean_run(tmp_path: Path) -> None:
    """Чистый прогон — код 0."""
    run = _run_with(tmp_path, "Обычный текст без находок.\n")
    assert main(["check_artifact_policy.py", str(run)]) == 0


def test_main_requires_argument() -> None:
    """Без аргумента — код 2 и подсказка по использованию."""
    assert main(["check_artifact_policy.py"]) == 2
