"""Генерация eval-конфига promptfoo: подстановка модели и абсолютные пути.

Зачем. `make eval` кладёт конфиг в корень репозитория, а `promptfoo`
разрешает относительные пути от каталога конфига. Поэтому все пути к
скриптам в сгенерированном конфиге должны быть абсолютными — иначе
прогон упадёт с «file not found».

Проверяется, что абсолютизируются ВСЕ провайдеры: не только
`gated_provider.py`, но и `multi_turn_provider.py`. Регрессия: многоходовый
провайдер был добавлен в шаблон конфига, но не в список обрабатываемых — и
реальный прогон падал бы на поиске файла.
"""

from __future__ import annotations

from make_eval_config import build_config

from idea_to_spec.paths import EVAL_CONFIG_FILE, REPO_ROOT


def _generated(model: str = "qwen3:8b") -> str:
    """Сгенерировать конфиг из шаблона репозитория.

    Args:
        model: Тег модели в Ollama.

    Returns:
        Текст сгенерированного конфига.
    """
    template = EVAL_CONFIG_FILE.read_text(encoding="utf-8")
    return build_config(template, model, REPO_ROOT)


def test_provider_paths_are_absolute() -> None:
    """Все exec-провайдеры получают абсолютный путь к скрипту."""
    config = _generated()
    for script in ("gated_provider.py", "multi_turn_provider.py"):
        assert f"exec:python3 {REPO_ROOT / 'scripts' / script}" in config, (
            f"{script}: путь не абсолютный — конфиг вне каталога eval/ упадёт"
        )


def test_no_relative_provider_paths_remain() -> None:
    """Относительных путей к провайдерам в конфиге не осталось."""
    config = _generated()
    assert "exec:python3 ../scripts/" not in config, (
        "в конфиге остался относительный путь к провайдеру"
    )


def test_tests_path_is_absolute() -> None:
    """Путь к набору кейсов — абсолютный."""
    config = _generated()
    assert f"tests: file://{REPO_ROOT / 'eval' / 'cases' / 'roles.jsonl'}" in config


def test_transform_vars_path_is_absolute() -> None:
    """Путь к трансформу переменных — абсолютный."""
    config = _generated()
    assert f"transformVars: file://{REPO_ROOT / 'scripts' / 'promptfoo_transform.py'}" in config


def test_model_is_substituted() -> None:
    """Тег модели подставляется в конфиг."""
    config = _generated("qwen2.5:7b")
    assert "model: qwen2.5:7b" in config
    assert "model: qwen3:8b" not in config


def test_thinking_model_gets_think_false() -> None:
    """Для thinking-модели режим рассуждений выключается."""
    config = _generated("qwen3:8b")
    assert "think: false" in config


def test_generated_config_keeps_provider_blocks() -> None:
    """Сгенерированный конфиг сохраняет блоки обоих провайдеров.

    YAML разбирается не библиотекой `pyyaml` (её нет в зависимостях
    eval-обвязки), а структурой шаблона: у каждого провайдера есть
    `- id:` и `label:`.
    """
    config = _generated()
    assert config.count("- id: exec:python3") == 2, (
        "ожидались два exec-провайдера: обычный и многоходовый"
    )
    assert "label: multi-turn" in config, "многоходовый провайдер потерялся при генерации"
    assert "label: qwen3-8b-gated" in config, "метка обычного провайдера потерялась"
