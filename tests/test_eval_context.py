"""Контекст eval-прогона: num_ctx задан явно и доезжает до Ollama.

Зачем. Ollama по умолчанию берёт `num_ctx=4096`. Замер 2026-11-26 на
`qwen3:8b`: промпт 46 КБ → `prompt_eval_count=4096`, инструкция из начала
промпта теряется, из конца — остаётся; при `num_predict=600` контекст
вытесняется во время генерации (`done_reason=length`). Полный промпт
оркестратора — 3766 токенов (92% окна 4096), системного аналитика — 3448.

Поэтому: конфиг eval обязан пинить `num_ctx`, а exec-провайдеры — передавать
его в тело запроса. Иначе длинные ответы ролей генерируются по усечённому
промпту, и eval измеряет не промпт, а артефакт вытеснения контекста.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_CONFIG = REPO_ROOT / "eval" / "promptfooconfig.yaml"
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


def test_providers_forward_num_ctx() -> None:
    """Оба exec-провайдера передают num_ctx в тело запроса к Ollama."""
    for path in PROVIDERS:
        source = path.read_text(encoding="utf-8")
        assert '"num_ctx"' in source, f"{path.name} не передаёт num_ctx"
