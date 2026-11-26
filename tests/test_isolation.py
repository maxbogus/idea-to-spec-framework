"""Контракты изоляции: фреймворк не читает ничего вне своего корня.

Зачем. Содержимое фреймворка переносится в чужой проект целиком (команда
`export`), поэтому любой путь вида `../...` — это утечка: на машине автора
он резолвится, у потребителя — нет. Тесты фиксируют три свойства:

- в Makefile и AGENTS.md нет ссылок на родительский каталог;
- экспорт (и dev-режим, и колесо) кладёт lock-файлы и лицензию: без них
  потребитель не может воспроизвести установку;
- `scaffold` уважает `OUT_ROOT`, иначе артефакты прогона нельзя держать
  вне каталога фреймворка.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from idea_to_spec.paths import REPO_ROOT

#: Файлы, без которых развёрнутый фреймворк не воспроизводим у потребителя.
REQUIRED_EXPORT_FILES = ("uv.lock", "package-lock.json", ".gitignore", "LICENSE")


def test_makefile_has_no_parent_dir_references() -> None:
    """Makefile не обращается к родительскому каталогу."""
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "../" not in text, (
        "Makefile ссылается на родительский каталог: у потребителя такого пути нет "
        "(исторический след monorepo/workshop)"
    )


def test_agents_md_has_no_parent_repo_instructions() -> None:
    """AGENTS.md не отправляет агента в родительский репозиторий."""
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "check-split" not in text, "AGENTS.md ссылается на цель родительского Makefile"
    assert "../docs/migration" not in text, "AGENTS.md ссылается на каталог вне фреймворка"


def test_tests_do_not_hardcode_tmp_paths() -> None:
    """Тесты не пишут в общий /tmp: путь должен приходить из tmp_path.

    Литерал собирается по частям, иначе тест находит сам себя.
    """
    needle = 'Path("/' + "tmp/"
    offenders = [
        path.name
        for path in sorted((REPO_ROOT / "tests").glob("*.py"))
        if needle in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"жёсткий /tmp в тестах (не работает на Windows): {offenders}"


def test_wheel_includes_lockfiles_and_license() -> None:
    """Колесо содержит lock-файлы и лицензию — паритет с dev-экспортом."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    force_include = data["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    missing = [name for name in REQUIRED_EXPORT_FILES if name not in force_include]
    assert not missing, (
        f"force-include не покрывает {missing}: установленный пакет развернёт дерево, "
        "отличное от dev-экспорта"
    )


def test_export_copies_lockfiles_and_license(tmp_path: Path) -> None:
    """Экспорт кладёт lock-файлы, .gitignore и LICENSE в целевой каталог."""
    from idea_to_spec_framework import export

    dest = tmp_path / "framework"
    export(dest)
    missing = [name for name in REQUIRED_EXPORT_FILES if not (dest / name).is_file()]
    assert not missing, f"экспорт потерял {missing}"


def test_gitattributes_pins_lf_for_scripts() -> None:
    """Git-атрибуты держат LF: иначе Windows-чекбокс ломает shebang."""
    path = REPO_ROOT / ".gitattributes"
    assert path.is_file(), "нет .gitattributes — CRLF при checkout сломает bash-скрипты"
    text = path.read_text(encoding="utf-8")
    for rule in ("*.sh text eol=lf", "Makefile text eol=lf", "*.mmd text eol=lf"):
        assert rule in text, f".gitattributes: нет правила {rule!r}"


def test_scaffold_honors_out_root(tmp_path: Path) -> None:
    """`scaffold-run.sh <run> <tier> <out-root>` создаёт прогон в out-root."""
    out_root = tmp_path / "specs"
    # Уникальный id: тест не должен зависеть от остатков прошлых прогонов.
    run_id = f"scaffold-{tmp_path.name}"
    subprocess.run(
        ["bash", "scripts/scaffold-run.sh", run_id, "base", str(out_root)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    assert (out_root / run_id / "brief.md").is_file()
    assert not (REPO_ROOT / "output" / run_id).exists(), "scaffold проигнорировал OUT_ROOT"


def test_makefile_python_is_configurable() -> None:
    """Интерпретатор Python переопределяем: на Windows нет `python3`."""
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "PYTHON ?=" in text, "нет переменной PYTHON — Windows-путь не запустится"
    assert "@python3 " not in text, "в рецептах остался жёсткий python3 вместо $(PYTHON)"
