"""Сгенерировать eval-конфиг promptfoo для указанной модели.

Зачем отдельный скрипт. Модель в `eval/promptfooconfig.yaml` была зашита
строкой: `ollama:chat:qwen3:8b`. Чтобы сравнивать модели (make eval
OLLAMA_MODEL=qwen3:8b) без правки конфига, конфиг генерируется из шаблона
с подстановкой тега модели.

Использование:
    uv run python scripts/make_eval_config.py --model qwen3:8b --out /tmp/cfg.yaml
    uv run python scripts/make_eval_config.py \
        --template eval/promptfooconfig.mock.yaml --out .eval-config-mock.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

#: Тег модели по умолчанию — та, на которой проходит основной прогон.
DEFAULT_MODEL = "qwen3:8b"


def _config_source(config_path: Path) -> str:
    """Прочитать шаблон конфига.

    Args:
        config_path: Путь к исходному конфигу.

    Returns:
        Текст конфига.
    """
    return config_path.read_text(encoding="utf-8")


#: Модели с «размышляющим» режимом: их шаблон чата по умолчанию включает
#: блок рассуждений перед ответом. Для eval это лишнее: нужен детерминированный
#: JSON, а рассуждение тратит токены и время.
#:
#: Измерено на qwen3:8b, один кейс: 365 с с рассуждением против 26.7 с без —
#: в 13.7 раза быстрее. Переменная окружения OLLAMA_DISABLE_THINKING не
#: подходит: сервер Ollama читает её только при старте, поэтому режим
#: выключается полем `think` в теле запроса.
THINKING_MODELS = ("qwen3", "deepseek-r1", "magistral", "granite3.3")


def _has_thinking(model: str) -> bool:
    """Проверить, включён ли у модели режим рассуждений по умолчанию.

    Args:
        model: Тег модели в Ollama.

    Returns:
        True, если режим рассуждений нужно отключить.
    """
    name = model.split(":")[0].lower()
    return any(name.startswith(prefix) for prefix in THINKING_MODELS)


#: Exec-провайдеры, путь к которым абсолютизируется при генерации конфига.
#: Ключ — фрагмент строки `- id:` в шаблоне, значение — имя скрипта.
#:
#: Путь обязан быть абсолютным: конфиг может лежать вне каталога `eval/`
#: (make eval кладёт его в корень репозитория), а promptfoo разрешает
#: относительные пути от каталога конфига.
EXEC_PROVIDERS: dict[str, str] = {
    "- id: exec:python3 ../scripts/gated_provider.py": "gated_provider.py",
    "- id: exec:python3 ../scripts/multi_turn_provider.py": "multi_turn_provider.py",
    "- id: exec:python3 ../scripts/mock_provider.py": "mock_provider.py",
}

#: Метки провайдеров, к которым подставляется тег модели.
#: Ключ — фрагмент строки `label:`, значение — признак «метка с моделью».
MODEL_LABELS = ("local", "gated")


def _js_string(value: str) -> str:
    """Строковый литерал JavaScript (кавычки и обратные слэши экранируются)."""
    return json.dumps(value, ensure_ascii=False)


def _file_uri(path: Path) -> str:
    """Абсолютный file-URI с экранированием пробелов и спецсимволов.

    На Windows путь `C:\\Users\\...` превращается в `file:///C:/Users/...`:
    иначе promptfoo не разберёт URI.
    """
    posix = path.resolve().as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return "file://" + quote(posix, safe="/:")


def _exec_command(script: Path) -> str:
    """Идентификатор exec-провайдера с абсолютным интерпретатором и путём.

    Интерпретатор берётся из `sys.executable`: на Windows `python3` может
    отсутствовать в PATH. Кавычки нужны для путей с пробелами.
    """
    return f'exec:"{sys.executable}" "{script.resolve()}"'


def build_config(template: str, model: str, repo_root: Path) -> str:
    """Подставить тег модели в конфиг promptfoo.

    Пути к тестам и к transformVars становятся абсолютными: конфиг может
    лежать вне репозитория (например, в /tmp при сравнении моделей), а
    promptfoo разрешает относительные пути от каталога конфига.

    Args:
        template: Текст шаблона конфига.
        model: Тег модели в Ollama (например, `qwen3:8b`).
        repo_root: Корень репозитория — для абсолютных путей.

    Returns:
        Текст конфига с подставленной моделью.
    """
    lines = template.splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- id: ollama:chat:"):
            # Провайдер с код-гейтом: пустая идея отсекается до вызова модели.
            # Путь абсолютный: конфиг может лежать вне каталога `eval/`
            # (make eval кладёт его в корень репозитория), а promptfoo
            # разрешает относительные пути от каталога конфига.
            out.append(f"  - id: {_exec_command(repo_root / 'scripts' / 'gated_provider.py')}")
            continue

        provider_script = None
        for marker, script in EXEC_PROVIDERS.items():
            if stripped.startswith(marker):
                provider_script = script
                break
        if provider_script is not None:
            out.append(f"  - id: {_exec_command(repo_root / 'scripts' / provider_script)}")
        elif stripped == "- __ITSF_GATED_LABEL__":
            # `defaultTest.providers`: кейс без поля `providers` идёт только к
            # обычному провайдеру. Метка должна следовать за моделью — иначе
            # `make eval OLLAMA_MODEL=qwen2.5:7b` не найдёт провайдера и
            # упадёт на валидации ссылок.
            out.append(f"    - {model.replace(':', '-')}-gated")
        elif stripped.startswith("label:") and any(part in stripped for part in MODEL_LABELS):
            out.append(f"    label: {model.replace(':', '-')}-gated")
        elif stripped.startswith("model:"):
            out.append(f"      model: {model}")
        elif stripped.startswith("transformVars: file://../scripts/"):
            out.append(
                f"    transformVars: {_file_uri(repo_root / 'scripts' / 'promptfoo_transform.py')}"
            )
        elif stripped.startswith("tests: file://./cases/"):
            out.append(f"tests: {_file_uri(repo_root / 'eval' / 'cases' / 'roles.jsonl')}")
        else:
            out.append(line)

    if _has_thinking(model):
        # Отключаем режим рассуждений: promptfoo передаёт `config.think` в тело
        # запроса Ollama (поле think). Для eval нужен детерминированный JSON,
        # а рассуждение тратит токены и время (измерено: 365 с → 26.7 с на
        # одном кейсе). Переменная окружения OLLAMA_DISABLE_THINKING не
        # подходит: сервер Ollama читает её только при старте.
        #
        # Ключ `think` должен встречаться ровно один раз: в шаблоне он уже
        # есть, а дубликат делает YAML невалидным (promptfoo падает с
        # «duplicate key»). Поэтому заменяем существующую строку, а не
        # добавляем новую.
        replaced = False
        for index, line in enumerate(out):
            if line.strip().startswith("think:"):
                out[index] = "      think: false"
                replaced = True
                break
        if not replaced:
            for index, line in enumerate(out):
                if line.strip().startswith("- id: ollama:chat:"):
                    out.insert(
                        index + 3,
                        "      # Режим рассуждений выключен: нужен детерминированный JSON.\n"
                        "      think: false",
                    )
                    replaced = True
                    break
        if not replaced and "ollama:chat" in template:
            raise ValueError("в шаблоне конфига нет провайдера ollama:chat")

    config = "\n".join(out) + "\n"
    # Плейсхолдеры в asserts: корень фреймворка и интерпретатор. Подстановка
    # идёт после сборки строки, чтобы не зависеть от расположения блока.
    # Неподставленный плейсхолдер виден как провал структурной проверки —
    # тихого поиска файлов от текущего каталога больше нет.
    config = config.replace("'__ITSF_ROOT__'", _js_string(repo_root.resolve().as_posix()))
    config = config.replace("'__ITSF_PYTHON__'", _js_string(sys.executable))
    return config


def main() -> int:
    """Сгенерировать конфиг и записать его в файл.

    Returns:
        Код возврата: 0 — успех.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Тег модели в Ollama")
    parser.add_argument("--template", type=Path, default=None, help="Путь к шаблону")
    parser.add_argument("--out", type=Path, required=True, help="Куда записать конфиг")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    template_path = args.template or repo_root / "eval" / "promptfooconfig.yaml"
    config = build_config(_config_source(template_path), args.model, repo_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(config, encoding="utf-8")
    print(f"config for {args.model} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
