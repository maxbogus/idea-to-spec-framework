"""Контекст eval-прогона: num_ctx задан явно и доезжает до Ollama.

Зачем. Ollama по умолчанию берёт `num_ctx=4096`. Замер 2026-11-26 на
`qwen3:8b`: промпт 46 КБ → `prompt_eval_count=4096`, инструкция из начала
промпта теряется, из конца — остаётся; при `num_predict=600` контекст
вытесняется во время генерации (`done_reason=length`). Полный промпт
оркестратора — 3766 токенов (92% окна 4096), системного аналитика — 3448.

Поэтому: конфиг eval обязан пинить `num_ctx`, а exec-провайдеры — передавать
его в тело запроса. Иначе длинные ответы ролей генерируются по усечённому
промпту, и eval измеряет не промпт, а артефакт вытеснения контекста.

После P0 (2026-11-26) параметры и вызов живут в одном модуле
(`idea_to_spec.ollama_client`), поэтому проверки ниже фиксируют две вещи:
конфиг пинит `num_ctx`, а провайдеры не собирают запрос сами — иначе пин
разъедется между ними, как это уже случилось однажды.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_CONFIG = REPO_ROOT / "eval" / "promptfooconfig.yaml"
CLIENT = REPO_ROOT / "scripts" / "idea_to_spec" / "ollama_client.py"
PROVIDERS = (
    REPO_ROOT / "scripts" / "gated_provider.py",
    REPO_ROOT / "scripts" / "multi_turn_provider.py",
)
MIN_CONTEXT = 8192


def _provider_configs() -> list[dict[str, Any]]:
    """Вернуть config-блоки всех провайдеров eval-конфига."""
    config = cast(dict[str, Any], yaml.safe_load(EVAL_CONFIG.read_text(encoding="utf-8")))
    return [cast(dict[str, Any], provider.get("config") or {}) for provider in config["providers"]]


def test_eval_config_pins_num_ctx() -> None:
    """У каждого провайдера eval-конфига задан num_ctx, и он не меньше 8192."""
    for config in _provider_configs():
        assert "num_ctx" in config, "провайдер без num_ctx: Ollama возьмёт 4096"
        assert int(config["num_ctx"]) >= MIN_CONTEXT


def test_providers_use_shared_client() -> None:
    """Оба exec-провайдера вызывают общий клиент, а не собирают запрос сами.

    Раньше `num_ctx` и параметры генерации дублировались в двух файлах: правка
    одного оставляла второй без пина. Теперь точка правды одна —
    `idea_to_spec.ollama_client`.
    """
    for path in PROVIDERS:
        source = path.read_text(encoding="utf-8")
        assert "ollama_client" in source, (
            f"{path.name} не использует общий клиент: параметры Ollama разъедутся"
        )


def test_client_pins_num_ctx_and_metadata() -> None:
    """Клиент пинит num_ctx и читает метаданные ответа, а не только текст."""
    source = CLIENT.read_text(encoding="utf-8")
    assert '"num_ctx"' in source, "клиент не передаёт num_ctx"
    assert "DEFAULT_NUM_CTX = 16384" in source
    for field in ("prompt_eval_count", "eval_count", "done_reason"):
        assert field in source, f"клиент не читает {field}: усечение будет невидимо"


def test_eval_targets_keep_call_traces() -> None:
    """`make eval` и `make eval-target` включают трассировку вызова.

    Без трейса замер прогона невоспроизводим: именно так замер «46 КБ → 4096»
    остался только в рукописном журнале (в репозитории `_raw` нет).
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert makefile.count("ITSF_TRACE=") >= 2, "трассировка не включена в eval-целях"
    assert makefile.count("ITSF_RAW_DIR=") >= 2, "сырые дампы не включены в eval-целях"


def test_trace_artifacts_are_gitignored() -> None:
    """Трейс и сырые дампы не попадают в git: это локальные артефакты замера."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "docs/evaluation/traces/" in gitignore
    assert "docs/evaluation/raw/" in gitignore
