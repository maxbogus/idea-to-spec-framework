"""Контракты реестра скилов (`skills/registry.yaml`).

Реестр — метаданные жизненного цикла скила: версия, область, входы/выходы,
зависимости, evals, владелец, риск. Без проверки он превращается в мёртвый
файл: скил добавлен, записи нет, зависимость не резолвится — и никто не
заметил.

Те же правила проверяет `scripts/check_skills_registry.py` (гейт
`make check-skills`); здесь — граничные случаи.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from check_skills_registry import check_registry, load_registry

#: Корень реального репозитория.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Минимальный валидный реестр для синтетического репозитория.
VALID = """schema: 1
skills:
  - name: collect-sources
    file: skills/collect-sources.md
    version: 1.0.0
    scope: "сбор источников с цитированием"
    inputs: ["бриф"]
    outputs: ["список источников"]
    dependencies: []
    evals: []
    owner: workshop-maintainer
    risk_level: medium
"""


def make_repo(
    root: Path,
    registry: str = VALID,
    skills: tuple[str, ...] = ("collect-sources",),
    cases: tuple[str, ...] = (),
) -> Path:
    """Собрать синтетический репозиторий с реестром и скилами."""

    skills_dir = root / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "README.md").write_text("# Skills\n", encoding="utf-8")
    (skills_dir / "registry.yaml").write_text(registry, encoding="utf-8")
    for name in skills:
        (skills_dir / f"{name}.md").write_text("# Skill\n", encoding="utf-8")
    cases_dir = root / "eval" / "cases"
    cases_dir.mkdir(parents=True)
    (cases_dir / "roles.jsonl").write_text(
        "\n".join(json.dumps({"metadata": {"id": case}}) for case in cases) + "\n",
        encoding="utf-8",
    )
    return root


def test_repo_registry_is_valid() -> None:
    """Реестр реального репозитория проходит проверку."""

    assert check_registry(REPO_ROOT) == []


def test_repo_registry_describes_every_skill() -> None:
    """Каждый `skills/*.md` (кроме README) попадает в реестр."""

    loaded = load_registry(REPO_ROOT / "skills" / "registry.yaml")
    described = {entry["file"] for entry in loaded["skills"]}
    on_disk = {
        f"skills/{path.name}"
        for path in (REPO_ROOT / "skills").glob("*.md")
        if path.name != "README.md"
    }
    assert described == on_disk


def test_skill_without_entry_is_reported(tmp_path: Path) -> None:
    """Скил на диске без записи — проблема."""

    root = make_repo(tmp_path, skills=("collect-sources", "extra-skill"))
    problems = check_registry(root)
    assert any("extra-skill" in problem for problem in problems), problems


def test_entry_for_missing_file_is_reported(tmp_path: Path) -> None:
    """Запись ссылается на несуществующий файл — проблема."""

    registry = VALID.replace("collect-sources.md", "ghost.md")
    root = make_repo(tmp_path, registry=registry)
    problems = check_registry(root)
    assert any("ghost.md" in problem for problem in problems), problems


def test_invalid_semver_is_reported(tmp_path: Path) -> None:
    """Версия не semver — проблема."""

    root = make_repo(tmp_path, registry=VALID.replace("1.0.0", "1.0"))
    problems = check_registry(root)
    assert any("semver" in problem or "версия" in problem for problem in problems), problems


def test_unresolved_dependency_is_reported(tmp_path: Path) -> None:
    """Зависимость на неизвестный скил — проблема."""

    registry = VALID.replace("dependencies: []", "dependencies: [ghost-skill]")
    root = make_repo(tmp_path, registry=registry)
    problems = check_registry(root)
    assert any("ghost-skill" in problem for problem in problems), problems


def test_self_dependency_is_reported(tmp_path: Path) -> None:
    """Скил не может зависеть от себя."""

    registry = VALID.replace("dependencies: []", "dependencies: [collect-sources]")
    root = make_repo(tmp_path, registry=registry)
    problems = check_registry(root)
    assert any("сам" in problem for problem in problems), problems


def test_unknown_risk_level_is_reported(tmp_path: Path) -> None:
    """Риск вне low/medium/high — проблема."""

    root = make_repo(tmp_path, registry=VALID.replace("risk_level: medium", "risk_level: huge"))
    problems = check_registry(root)
    assert any("risk_level" in problem for problem in problems), problems


def test_dependency_cycle_is_reported(tmp_path: Path) -> None:
    """Цикл зависимостей — проблема."""

    second = (
        "  - name: second-skill\n"
        "    file: skills/second-skill.md\n"
        "    version: 1.0.0\n"
        '    scope: "второй"\n'
        '    inputs: ["бриф"]\n'
        '    outputs: ["результат"]\n'
        "    dependencies: [collect-sources]\n"
        "    evals: []\n"
        "    owner: workshop-maintainer\n"
        "    risk_level: low\n"
    )
    registry = VALID.replace("dependencies: []", "dependencies: [second-skill]") + second
    root = make_repo(tmp_path, registry=registry, skills=("collect-sources", "second-skill"))
    problems = check_registry(root)
    assert any("цикл" in problem for problem in problems), problems


def test_duplicate_name_is_reported(tmp_path: Path) -> None:
    """Две записи с одним именем — проблема."""

    registry = VALID + VALID.split("skills:\n", 1)[1]
    root = make_repo(tmp_path, registry=registry)
    problems = check_registry(root)
    assert any("повтор" in problem for problem in problems), problems


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    """Отсутствующее обязательное поле — проблема."""

    registry = "\n".join(
        line for line in VALID.splitlines() if not line.strip().startswith("owner:")
    )
    root = make_repo(tmp_path, registry=registry + "\n")
    problems = check_registry(root)
    assert any("owner" in problem for problem in problems), problems


def test_empty_scope_is_reported(tmp_path: Path) -> None:
    """Пустая область — проблема."""

    root = make_repo(tmp_path, registry=VALID.replace('"сбор источников с цитированием"', '""'))
    problems = check_registry(root)
    assert any("scope" in problem for problem in problems), problems


def test_unknown_eval_reference_is_reported(tmp_path: Path) -> None:
    """Evals ссылается на несуществующий кейс — проблема."""

    registry = VALID.replace("evals: []", "evals: [NOPE-99]")
    root = make_repo(tmp_path, registry=registry)
    problems = check_registry(root)
    assert any("NOPE-99" in problem for problem in problems), problems


def test_eval_case_reference_is_accepted(tmp_path: Path) -> None:
    """Evals на существующий eval-кейс принимается."""

    registry = VALID.replace("evals: []", "evals: [FC-01-three-statuses]")
    root = make_repo(tmp_path, registry=registry, cases=("FC-01-three-statuses",))
    assert check_registry(root) == []


def test_missing_registry_is_reported(tmp_path: Path) -> None:
    """Файла реестра нет — проблема."""

    root = make_repo(tmp_path)
    (root / "skills" / "registry.yaml").unlink()
    problems = check_registry(root)
    assert any("registry.yaml" in problem for problem in problems), problems


def test_invalid_yaml_is_reported(tmp_path: Path) -> None:
    """Невалидный YAML — проблема, а не падение."""

    root = make_repo(tmp_path, registry="skills: [\n")
    problems = check_registry(root)
    assert any("YAML" in problem for problem in problems), problems


@pytest.mark.parametrize("version", ["0.1.0", "1.2.3", "2.0.0-rc.1"])
def test_semver_accepts_valid_versions(tmp_path: Path, version: str) -> None:
    """Корректные semver-версии принимаются."""

    root = make_repo(tmp_path, registry=VALID.replace("1.0.0", version))
    assert check_registry(root) == []
