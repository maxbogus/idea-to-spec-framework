"""Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


class NoRunsError(RuntimeError):
    """Прогоны не найдены: проверять нечего, и это не тихий успех."""


def _disk_runs(root: Path) -> list[str]:
    """Прогоны, лежащие на диске (каталоги верхнего уровня).

    Служебные каталоги (`.git`) прогонами не считаются.
    """
    return sorted(
        path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")
    )


def _git_runs(root: Path) -> list[str]:
    """Прогоны, отслеживаемые git внутри root.

    Returns:
        Отсортированные идентификаторы прогонов; пустой список — git не
        применим (не репозиторий) или под root ничего не отслеживается.

    Raises:
        NoRunsError: git недоступен.
    """
    if shutil.which("git") is None:
        return []
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return []
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0:
        return []
    return sorted({line.split("/", 1)[0] for line in listed.stdout.splitlines() if line.strip()})


def discover_runs(root: Path) -> list[str]:
    """Определить, какие прогоны проверять.

    Логика: отслеживаемые git прогоны приоритетны (свежий scaffold содержит
    placeholder-ID и по определению не проходит `check_run`). Если git не
    применим или ничего не отслеживает, берутся каталоги с диска — иначе
    непроверенные прогоны молча выпадали бы из гейта.

    Args:
        root: Каталог прогонов (`OUT_ROOT`).

    Returns:
        Отсортированные идентификаторы прогонов.

    Raises:
        NoRunsError: каталога нет, либо в нём нет ни одного прогона.
    """
    if not root.is_dir():
        raise NoRunsError(f"нет каталога прогонов: {root}")

    runs = _git_runs(root) or _disk_runs(root)
    if not runs:
        raise NoRunsError(
            f"в {root} нет прогонов: сначала `make scaffold RUN=<id>`, "
            "затем `make check-run RUN=<id>`"
        )
    return runs


def main(argv: list[str] | None = None) -> int:
    """Напечатать список прогонов (по одному в строке)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="output", help="каталог прогонов")
    args = parser.parse_args(argv)

    try:
        runs = discover_runs(Path(args.root))
    except NoRunsError as error:
        print(f"check-runs: FAILED — {error}", file=sys.stderr)
        return 1

    for run in runs:
        print(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
