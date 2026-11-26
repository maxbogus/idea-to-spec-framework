"""Контракт: паки диаграмм в `scripts/scaffold-run.sh`.

Зачем. Паки включаются только явно, но именно поэтому легко получить
«PACKS=ai добавил полсистемы» или «опечатка в имени пака прошла молча».
Тесты фиксируют точный состав: base + запрошенные паки, `all` = всё,
неизвестный пак — ошибка, старый вызов с out-root продолжает работать.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from check_dor import BASE_DIAGRAMS, EXTENDED_DIAGRAMS, PACK_DIAGRAMS
from idea_to_spec.paths import REPO_ROOT


def _scaffold(run_id: str, tier: str, packs: str, out_root: Path) -> subprocess.CompletedProcess[str]:
    """Развернуть каркас во временный каталог.

    Args:
        run_id: Идентификатор прогона.
        tier: Уровень (`base`, `full`, `all`).
        packs: Список паков через запятую (может быть пустым).
        out_root: Каталог, куда писать прогон.

    Returns:
        Результат запуска скрипта.
    """
    return subprocess.run(
        ["bash", "scripts/scaffold-run.sh", run_id, tier, packs, str(out_root)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _diagrams(out_root: Path, run_id: str) -> set[str]:
    """Имена `.mmd` в прогоне без расширения."""
    return {path.stem for path in (out_root / run_id / "diagrams").glob("*.mmd")}


def test_pack_ai_adds_only_requested_diagrams(tmp_path: Path) -> None:
    """`PACKS=data,ai` = база + ровно диаграммы этих двух паков."""
    result = _scaffold("run", "base", "data,ai", tmp_path)

    assert result.returncode == 0, result.stderr
    expected = set(BASE_DIAGRAMS) | set(PACK_DIAGRAMS["data"]) | set(PACK_DIAGRAMS["ai"])
    assert _diagrams(tmp_path, "run") == expected


def test_full_tier_does_not_add_packs(tmp_path: Path) -> None:
    """`full` остаётся базой + расширенным уровнем, без паков."""
    result = _scaffold("run", "full", "", tmp_path)

    assert result.returncode == 0, result.stderr
    assert _diagrams(tmp_path, "run") == set(BASE_DIAGRAMS) | set(EXTENDED_DIAGRAMS)


def test_all_tier_includes_every_pack(tmp_path: Path) -> None:
    """`all` = база + расширенный уровень + все паки."""
    result = _scaffold("run", "all", "", tmp_path)

    assert result.returncode == 0, result.stderr
    expected = set(BASE_DIAGRAMS) | set(EXTENDED_DIAGRAMS)
    for diagrams in PACK_DIAGRAMS.values():
        expected |= set(diagrams)
    assert _diagrams(tmp_path, "run") == expected


def test_unknown_pack_fails_loudly(tmp_path: Path) -> None:
    """Опечатка в имени пака — код возврата и список допустимых."""
    result = _scaffold("run", "base", "nope", tmp_path)

    assert result.returncode != 0
    assert "unknown pack" in result.stderr
    assert not (tmp_path / "run").exists()


def test_legacy_out_root_argument_still_works(tmp_path: Path) -> None:
    """Старый трёхаргументный вызов (run, tier, out-root) не ломается."""
    result = subprocess.run(
        ["bash", "scripts/scaffold-run.sh", "run", "base", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "run" / "diagrams" / "use-case.mmd").is_file()
