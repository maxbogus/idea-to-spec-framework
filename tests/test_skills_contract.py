"""Контракт Cline-скила: frontmatter, бюджет тела, references.

Скил — самодостаточный каталог `skills/<name>/SKILL.md`. Frontmatter нужен,
чтобы скил находился по описанию; `references/` — чтобы тяжёлые каталоги и
примеры не попадали в контекст вместе с телом; бюджет тела не даёт скилу
разрастись обратно в монолит.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from check_skills_registry import check_registry

#: Корень реального репозитория.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Максимум строк тела скила (без frontmatter).
MAX_BODY_LINES = 60

#: Минимальный валидный реестр для синтетического репозитория.
VALID = """schema: 2
skills:
  - name: collect-sources
    file: skills/collect-sources/SKILL.md
    version: 1.0.0
    kind: procedure
    stage: business
    gate: ba_gate
    check: eval/cases/roles.jsonl
    scope: "сбор источников с цитированием"
    inputs: ["бриф"]
    outputs: ["список источников"]
    dependencies: []
    evals: []
    owner: workshop-maintainer
    risk_level: medium
"""


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Разделить `SKILL.md` на frontmatter и тело."""

    assert text.startswith("---\n"), "нет frontmatter"
    _, raw, body = text.split("---", 2)
    loaded = yaml.safe_load(raw)
    assert isinstance(loaded, dict), "frontmatter не объект"
    return loaded, body


def make_repo(
    root: Path,
    registry: str = VALID,
    *,
    frontmatter: bool = True,
    body_lines: int = 1,
    name: str = "collect-sources",
    references: tuple[str, ...] = (),
) -> Path:
    """Собрать синтетический репозиторий с одним скилом."""

    skills_dir = root / "skills"
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    (skills_dir / "README.md").write_text("# Skills\n", encoding="utf-8")
    (skills_dir / "registry.yaml").write_text(registry, encoding="utf-8")
    meta = (
        "---\n"
        f"name: {name}\n"
        "description: test skill\n"
        "allowed-tools: Read\n"
        "---\n\n"
        if frontmatter
        else ""
    )
    body = "\n".join(f"line {index}" for index in range(body_lines))
    (skill_dir / "SKILL.md").write_text(meta + body + "\n", encoding="utf-8")
    for relative in references:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# reference\n", encoding="utf-8")
    return root


def test_repo_skills_satisfy_contract() -> None:
    """Каждый скил репозитория: frontmatter, бюджет тела, описание."""

    skill_files = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
    assert skill_files, "в skills/ нет ни одного SKILL.md"
    for path in skill_files:
        meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        assert meta.get("name") == path.parent.name, path
        description = meta.get("description")
        assert isinstance(description, str) and description.strip(), path
        tools = meta.get("allowed-tools")
        assert isinstance(tools, str) and tools.strip(), path
        body_lines = len(body.strip("\n").splitlines())
        assert body_lines <= MAX_BODY_LINES, f"{path}: {body_lines} строк > {MAX_BODY_LINES}"


def test_missing_frontmatter_is_reported(tmp_path: Path) -> None:
    """Скил без frontmatter — проблема."""

    root = make_repo(tmp_path, frontmatter=False)
    problems = check_registry(root)
    assert any("frontmatter" in problem for problem in problems), problems


def test_frontmatter_name_mismatch_is_reported(tmp_path: Path) -> None:
    """`name` во frontmatter не совпадает с каталогом — проблема."""

    root = make_repo(tmp_path, name="collect-sources")
    skill = root / "skills" / "collect-sources" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8").replace("name: collect-sources", "name: other"),
        encoding="utf-8",
    )
    problems = check_registry(root)
    assert any("frontmatter" in problem and "name" in problem for problem in problems), problems


def test_body_over_budget_is_reported(tmp_path: Path) -> None:
    """Тело длиннее бюджета — проблема."""

    root = make_repo(tmp_path, body_lines=MAX_BODY_LINES + 1)
    problems = check_registry(root)
    assert any("строк" in problem for problem in problems), problems


def test_flat_skill_file_is_reported(tmp_path: Path) -> None:
    """Плоский файл в skills/ — не скил: нужен каталог с SKILL.md."""

    root = make_repo(tmp_path)
    (root / "skills" / "flat-skill.md").write_text("# Skill\n", encoding="utf-8")
    problems = check_registry(root)
    assert any("плоский" in problem for problem in problems), problems


def test_missing_reference_is_reported(tmp_path: Path) -> None:
    """`references` на несуществующий файл — проблема."""

    registry = VALID.replace(
        "evals: []",
        "evals: []\n    references: [skills/collect-sources/references/missing.md]",
    )
    root = make_repo(tmp_path, registry=registry)
    problems = check_registry(root)
    assert any("references" in problem for problem in problems), problems


def test_reference_outside_skill_dir_is_reported(tmp_path: Path) -> None:
    """`references` вне каталога скила — проблема."""

    registry = VALID.replace(
        "evals: []",
        "evals: []\n    references: [templates/outside.md]",
    )
    root = make_repo(tmp_path, registry=registry, references=("templates/outside.md",))
    problems = check_registry(root)
    assert any("references" in problem and "вне" in problem for problem in problems), problems
