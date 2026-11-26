"""Генерация eval-конфига promptfoo: подстановка модели и абсолютные пути.

Зачем. `make eval` и `make eval-mock` кладут конфиг в корень репозитория, а
`promptfoo` разрешает относительные пути от каталога конфига. Поэтому все
пути к скриптам в сгенерированном конфиге должны быть абсолютными — иначе
прогон упадёт с «file not found».

Портируемость: интерпретатор берётся из `sys.executable` (на Windows
`python3` может не существовать), пути к файлам — URI с экранированием
пробелов, а корень фреймворка подставляется вместо плейсхолдера
`'__ITSF_ROOT__'`. Без подстановки структурная проверка падает громко, а не
ищет файлы от текущего каталога.
"""

from __future__ import annotations

import sys

import pytest

from idea_to_spec.paths import EVAL_CONFIG_FILE, EVAL_DIR, REPO_ROOT
from make_eval_config import build_config

MOCK_CONFIG_FILE = EVAL_DIR / "promptfooconfig.mock.yaml"


def _generated(model: str = "qwen3:8b") -> str:
    """Сгенерировать конфиг из шаблона реального прогона.

    Args:
        model: Тег модели в Ollama.

    Returns:
        Текст сгенерированного конфига.
    """
    template = EVAL_CONFIG_FILE.read_text(encoding="utf-8")
    return build_config(template, model, REPO_ROOT)


def test_provider_paths_are_absolute() -> None:
    """Все exec-провайдеры получают абсолютный путь к скрипту и интерпретатор."""
    config = _generated()
    for script in ("gated_provider.py", "multi_turn_provider.py"):
        expected = f'exec:"{sys.executable}" "{REPO_ROOT / "scripts" / script}"'
        assert expected in config, f"{script}: путь не абсолютный — конфиг вне eval/ упадёт"


def test_no_hardcoded_python_remains() -> None:
    """Жёсткого `python3` в конфиге нет: на Windows его может не быть."""
    config = _generated()
    assert "exec:python3 " not in config, "остался жёсткий python3 — Windows не запустится"


def test_root_and_python_placeholders_are_substituted() -> None:
    """Плейсхолдеры корня и интерпретатора заменены реальными значениями."""
    config = _generated()
    assert "__ITSF_ROOT__" not in config, "корень фреймворка не подставлен"
    assert "__ITSF_PYTHON__" not in config, "интерпретатор не подставлен"


def test_tests_path_is_an_absolute_uri() -> None:
    """Путь к набору кейсов — абсолютный file-URI без пробелов."""
    line = next(line for line in _generated().splitlines() if line.startswith("tests:"))
    uri = line.split("tests:", 1)[1].strip()
    assert uri.startswith("file:///"), f"не абсолютный URI: {line}"
    assert "cases/roles.jsonl" in uri
    assert " " not in uri, f"в URI остался пробел: {line}"


def test_transform_vars_path_is_an_absolute_uri() -> None:
    """Путь к трансформу переменных — абсолютный file-URI."""
    line = next(
        line for line in _generated().splitlines() if line.strip().startswith("transformVars:")
    )
    assert "file:///" in line, f"не абсолютный URI: {line}"
    assert "promptfoo_transform.py" in line


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
    assert config.count("- id: exec:") == 2, "ожидались два exec-провайдера: обычный и многоходовый"
    assert "label: multi-turn" in config, "многоходовый провайдер потерялся при генерации"
    assert "label: qwen3-8b-gated" in config, "метка обычного провайдера потерялась"


def test_mock_template_is_generated_without_model() -> None:
    """Mock-конфиг генерируется тем же путём: без модели и без ollama-провайдера."""
    template = MOCK_CONFIG_FILE.read_text(encoding="utf-8")
    config = build_config(template, "qwen3:8b", REPO_ROOT)

    assert config.count("- id: exec:") == 2, "в mock-конфиге должны быть оба mock-провайдера"
    assert "mock_provider.py" in config
    assert f'"{sys.executable}"' in config
    assert "__ITSF_ROOT__" not in config
    assert "ollama:chat" not in config


def test_default_test_pins_single_turn_provider() -> None:
    """Кейс без `providers` идёт только к обычному провайдеру, а не к обоим.

    Зачем. В шаблоне два провайдера (обычный и многоходовый), и promptfoo
    подставляет `test.providers ?? defaultTest.providers`. Без
    `defaultTest.providers` каждый обычный кейс уходил к обоим провайдерам:
    отчёт получал два замера на кейс (35 кейсов → 68 результатов), а
    `test_real_model_meets_contract` читал первый попавшийся замер. На
    кейсе-пустой-идее (NEG-01) это давало ложную «регрессию»: код-гейт живёт
    только в `gated_provider.py`, а многоходовый провайдер его не применяет.
    """
    config = _generated("qwen3:8b")
    assert "defaultTest:" in config, "нет блока defaultTest — кейсы пойдут к обоим провайдерам"
    assert "- qwen3-8b-gated" in config, "обычный провайдер не закреплён за кейсами по умолчанию"
    assert "__ITSF_GATED_LABEL__" not in config, "плейсхолдер метки не подставлен"

    other = _generated("qwen2.5:7b")
    assert "- qwen2.5-7b-gated" in other, "метка обычного провайдера не следует за моделью"


def test_mock_config_pins_replay_provider() -> None:
    """В mock-конфиге кейсы без `providers` идут только к replay-провайдеру."""
    template = MOCK_CONFIG_FILE.read_text(encoding="utf-8")
    config = build_config(template, "qwen3:8b", REPO_ROOT)
    assert "defaultTest:" in config, "в mock-конфиге нет defaultTest — кейсы пойдут к обоим провайдерам"
    assert "- deterministic-replay" in config, "replay-провайдер не закреплён за кейсами по умолчанию"


@pytest.mark.parametrize("config_name", ["promptfooconfig.yaml", "promptfooconfig.mock.yaml"])
def test_templates_declare_root_placeholders(config_name: str) -> None:
    """Шаблоны объявляют плейсхолдеры и не зависят от текущего каталога."""
    text = (EVAL_DIR / config_name).read_text(encoding="utf-8")
    assert "'__ITSF_ROOT__'" in text, f"{config_name}: нет плейсхолдера корня"
    assert "'__ITSF_PYTHON__'" in text, f"{config_name}: нет плейсхолдера интерпретатора"
    assert "process.cwd()" not in text, (
        f"{config_name}: путь считается от cwd — запуск из чужого каталога сломается"
    )
    assert "semantic_check_bridge.py" in text
