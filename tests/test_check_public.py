"""Контракты public-сканера: личные пути, секреты, внешние зависимости.

Фреймворк публикуется как MIT-пакет. Сканер — сеть, а не гарантия: он ловит
известные маркеры, которые нельзя коммитить (домашние пути, токены, ключи)
и ссылки на личную конфигурацию Cline, от которой фреймворк обязан быть
независим.
"""

from __future__ import annotations

from pathlib import Path

from check_public import check_public, scan_text


def test_personal_path_is_detected() -> None:
    """Абсолютный домашний путь — находка."""

    assert scan_text("см. /home/alice/project/spec.md")


def test_github_token_is_detected() -> None:
    """GitHub-токен — находка."""

    assert scan_text("token=ghp_" + "a" * 30)


def test_private_key_is_detected() -> None:
    """Заголовок приватного ключа — находка."""

    assert scan_text("-----BEGIN RSA PRIVATE KEY-----")


def test_external_cline_reference_is_detected() -> None:
    """Ссылка на личный `~/.cline` или playbook — находка."""

    assert scan_text("см. ~/.cline/skills/plan-self-check")
    assert scan_text("источник: cline-agent-playbook")


def test_clean_text_has_no_findings() -> None:
    """Обычный текст фреймворка чист."""

    assert scan_text("Требование FR-1 ссылается на BR-1 и AC-1.") == []


def test_forbidden_suffix_is_reported(tmp_path: Path) -> None:
    """`.env` в индексе git — ошибка, даже если содержимое пустое."""

    (tmp_path / ".env").write_text("", encoding="utf-8")
    problems = check_public(tmp_path, tracked=[".env"])
    assert any(".env" in problem for problem in problems), problems


def test_tracked_file_with_token_is_reported(tmp_path: Path) -> None:
    """Токен в отслеживаемом файле — ошибка."""

    (tmp_path / "notes.md").write_text("ghp_" + "b" * 30, encoding="utf-8")
    problems = check_public(tmp_path, tracked=["notes.md"])
    assert any("github token" in problem for problem in problems), problems


def test_clean_repository_passes(tmp_path: Path) -> None:
    """Чистый набор файлов проходит."""

    (tmp_path / "README.md").write_text("framework\n", encoding="utf-8")
    assert check_public(tmp_path, tracked=["README.md"]) == []
