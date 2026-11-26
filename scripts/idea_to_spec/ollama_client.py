"""Клиент Ollama для exec-провайдеров eval: вызов, трассировка, guard контекста.

Зачем отдельный модуль. Оба провайдера (`gated_provider`, `multi_turn_provider`)
вызывали Ollama сами и **выбрасывали метаданные ответа**: `prompt_eval_count`,
`eval_count`, `done_reason`. Из-за этого вытеснение контекста (дефект №1 волны C)
было невидимо изнутри прогона, а битый JSON (дефект №9) нельзя было отличить от
обрыва по `num_predict`. Замер 2026-11-26: промпт 46 КБ → `prompt_eval_count=4096`
при `num_ctx` по умолчанию, инструкция из начала промпта терялась.

Что здесь есть:

- `build_request` — тело запроса из `config` провайдера (единая точка правды по
  `num_ctx` / `num_predict` / `temperature` / `top_p` / `think`);
- `parse_reply` — разбор ответа вместе с метаданными, а не только текстом;
- `context_problems` / `enforce_context` — громкий отказ, если промпт вытеснен
  или ответ обрезан, вместо молчаливого артефакта;
- `extract_json_object` / `call_json` — контракт «ответ роли — JSON-объект» с
  одним ремонтным повтором;
- `record_call` — пер-вызовный трейс (JSONL) и сырой дамп промпта/ответа, чтобы
  главный замер прогона можно было воспроизвести. Запись несёт `ts` (UTC) и
  `call` (кейс + номер хода): без них append-only трейс на тег модели
  не атрибутируется. Включается переменными окружения `ITSF_TRACE` и
  `ITSF_RAW_DIR`: без них поведение прежнее.

Переменные окружения:

- `OLLAMA_URL` — адрес Ollama (по умолчанию `http://localhost:11434`);
- `ITSF_TRACE` — путь к JSONL-файлу трейса (append-only);
- `ITSF_RAW_DIR` — каталог для сырых дампов «промпт + ответ»;
- `ITSF_ALLOW_TRUNCATION=1` — не падать на вытеснении/обрезке (для замеров,
  которые специально исследуют это поведение);
- `ITSF_JSON_RETRY=0` — отключить ремонтный повтор при невалидном JSON.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

#: Контекст по умолчанию. Значение измерено: Ollama без `num_ctx` берёт 4096 и
#: вытесняет начало промпта; 16384 вмещает промпт оркестратора (3766 токенов)
#: и 3500 токенов ответа при VRAM 7.3 ГБ из 8.1 на `qwen3:8b` Q4.
DEFAULT_NUM_CTX = 16384
#: Предел ответа по умолчанию: 2000 токенов обрезали JSON ролей.
DEFAULT_NUM_PREDICT = 3500

TRACE_ENV = "ITSF_TRACE"
RAW_ENV = "ITSF_RAW_DIR"
ALLOW_TRUNCATION_ENV = "ITSF_ALLOW_TRUNCATION"
JSON_RETRY_ENV = "ITSF_JSON_RETRY"

#: Дописывается к промпту при ремонтном повторе. Короткая формулировка и
#: императив: длинное разъяснение после основного промпта не читается (F022).
REPAIR_SUFFIX = (
    "\n\nПРЕДЫДУЩИЙ ОТВЕТ БЫЛ НЕВАЛИДНЫМ JSON. Верни ТОЛЬКО один JSON-объект "
    "в формате роли: без текста вокруг, все строки закрыты."
)


class ContextTruncatedError(RuntimeError):
    """Промпт вытеснен или ответ обрезан — измерять нечего, ответ недостоверен."""


@dataclass(frozen=True)
class OllamaReply:
    """Ответ Ollama вместе с метаданными генерации.

    Attributes:
        text: Текст ответа модели.
        model: Тег модели, которой задавали вопрос.
        prompt_eval_count: Сколько токенов промпта модель реально увидела.
        eval_count: Сколько токенов ответа сгенерировано.
        done_reason: Причина остановки (`stop`, `length`, ...).
    """

    text: str
    model: str
    prompt_eval_count: int
    eval_count: int
    done_reason: str


def config_of(options: Mapping[str, Any]) -> dict[str, Any]:
    """Вернуть `config` провайдера promptfoo.

    Args:
        options: Второй аргумент exec-провайдера (`{"config": {...}}`).

    Returns:
        Словарь конфигурации (пустой, если его нет).
    """
    raw_config = options.get("config")
    return dict(raw_config) if isinstance(raw_config, Mapping) else {}


def _param(config: Mapping[str, Any], name: str, fallback: Any, alias: str | None = None) -> Any:
    """Взять параметр из `config` или его alias внутри `generation`.

    Args:
        config: Конфигурация провайдера.
        name: Имя параметра в `config`.
        fallback: Значение по умолчанию.
        alias: Имя того же параметра внутри блока `generation` (например,
            `max_tokens` вместо `num_predict`).

    Returns:
        Значение параметра.
    """
    if name in config:
        return config[name]
    generation = config.get("generation")
    if alias is not None and isinstance(generation, Mapping):
        return cast(Mapping[str, Any], generation).get(alias, fallback)
    return fallback


def build_request(
    prompt: str,
    options: Mapping[str, Any],
    history: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Собрать тело запроса к `/api/chat`.

    Args:
        prompt: Текст промпта (последнее сообщение пользователя).
        options: Второй аргумент exec-провайдера.
        history: История переписки (`assistant` — реплики модели, `user` —
            ответы заказчика); на первом ходе пустая.

    Returns:
        Тело запроса: модель, сообщения, `stream=False`, `options` и `think`.
    """
    config = config_of(options)
    model = str(config.get("model") or os.environ.get("OLLAMA_MODEL", "qwen3:8b"))

    messages: list[dict[str, str]] = [dict(message) for message in (history or [])]
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": _param(config, "temperature", 0),
            "num_predict": _param(config, "num_predict", DEFAULT_NUM_PREDICT, "max_tokens"),
            "top_p": _param(config, "top_p", 1),
            # Ollama без num_ctx берёт 4096: при длинном ответе окно
            # переполняется и начало промпта вытесняется (замер 2026-11-26).
            "num_ctx": _param(config, "num_ctx", DEFAULT_NUM_CTX),
        },
    }
    if "think" in config:
        body["think"] = config["think"]
    # Структурный вывод Ollama. Выключен по умолчанию: включается только после
    # целевого A/B-замера, иначе меняется и качество содержания, и метрика.
    if config.get("json_mode") is True:
        body["format"] = "json"
    return body


def parse_reply(payload: Mapping[str, Any], model: str = "") -> OllamaReply:
    """Разобрать ответ `/api/chat`, сохранив метаданные генерации.

    Args:
        payload: JSON-ответ Ollama.
        model: Тег модели (для записей, где Ollama его не вернула).

    Returns:
        Ответ с текстом и счётчиками токенов.
    """
    message = payload.get("message")
    text = ""
    if isinstance(message, Mapping):
        content = cast(Mapping[str, Any], message).get("content")
        text = str(content or "")
    return OllamaReply(
        text=text,
        model=str(payload.get("model") or model),
        prompt_eval_count=int(payload.get("prompt_eval_count") or 0),
        eval_count=int(payload.get("eval_count") or 0),
        done_reason=str(payload.get("done_reason") or ""),
    )


def context_problems(reply: OllamaReply, options: Mapping[str, Any]) -> list[str]:
    """Найти признаки вытеснения промпта или обрезки ответа.

    Args:
        reply: Ответ модели с метаданными.
        options: Второй аргумент exec-провайдера (оттуда берутся лимиты).

    Returns:
        Список проблем; пустой список — генерация прошла в пределах окна.
    """
    config = config_of(options)
    num_ctx = int(_param(config, "num_ctx", DEFAULT_NUM_CTX))
    num_predict = int(_param(config, "num_predict", DEFAULT_NUM_PREDICT, "max_tokens"))

    problems: list[str] = []
    # Ollama считает prompt_eval_count уже после усечения: равенство окну
    # означает, что начало промпта модель не видела.
    if reply.prompt_eval_count >= num_ctx:
        problems.append(
            f"промпт вытеснен: prompt_eval_count={reply.prompt_eval_count} при num_ctx={num_ctx}"
        )
    if reply.done_reason == "length":
        problems.append(
            f"ответ обрезан: done_reason=length при num_predict={num_predict} "
            f"(сгенерировано {reply.eval_count})"
        )
    used = reply.prompt_eval_count + reply.eval_count
    if used > num_ctx:
        problems.append(f"окно переполнено во время генерации: {used} > num_ctx={num_ctx}")
    return problems


def enforce_context(reply: OllamaReply, options: Mapping[str, Any]) -> None:
    """Упасть, если промпт вытеснен или ответ обрезан.

    Молчаливый артефакт из усечённого промпта — это и есть дефект, который
    волна C искала руками. Отключение — `ITSF_ALLOW_TRUNCATION=1`.

    Args:
        reply: Ответ модели с метаданными.
        options: Второй аргумент exec-провайдера.

    Raises:
        ContextTruncatedError: Есть признаки усечения, а проверка не отключена.
    """
    problems = context_problems(reply, options)
    if not problems or os.environ.get(ALLOW_TRUNCATION_ENV) == "1":
        return
    raise ContextTruncatedError(
        "; ".join(problems)
        + ". Увеличьте num_ctx или сократите промпт; "
        + f"{ALLOW_TRUNCATION_ENV}=1 отключает проверку."
    )


def strip_fences(text: str) -> str:
    """Снять markdown-обёртку ```json ... ``` вокруг ответа.

    Args:
        text: Текст ответа модели.

    Returns:
        Текст без обёртки.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    without_open = stripped.split("\n", 1)[1] if "\n" in stripped else ""
    if without_open.rstrip().endswith("```"):
        without_open = without_open.rstrip()[: -len("```")]
    return without_open.strip()


def _array_before_object(body: str) -> bool:
    """Стоит ли на верхнем уровне ответа массив, а не объект.

    Одного `startswith("[")` мало: ответ «Вот: [{"a": 1}]» начинается с текста,
    и поиск от первой `{` до последней `}` возвращал объект из массива —
    нарушение формата проходило как валидный ответ. Здесь проверяется, что `[`
    раньше первого `{` и что с этой позиции действительно разбирается
    JSON-массив (иначе скобка — часть прозы, например «[см. ниже]»).

    Args:
        body: Ответ модели без markdown-обёртки.

    Returns:
        True, если верхний уровень ответа — массив.
    """
    bracket = body.find("[")
    if bracket == -1:
        return False
    first_object = body.find("{")
    if first_object != -1 and first_object < bracket:
        return False
    try:
        parsed, _ = json.JSONDecoder().raw_decode(body[bracket:])
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, list)


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Извлечь JSON-объект из ответа модели.

    Проверяются два кандидата: ответ без markdown-обёртки и фрагмент от первой
    `{` до последней `}` — модель иногда добавляет строку до или после JSON.

    Args:
        text: Текст ответа модели.

    Returns:
        Разобранный объект или None, если валидного JSON-объекта нет.
    """
    candidates = [strip_fences(text)]
    # Массив на верхнем уровне — не ответ роли: извлекать из него первый объект
    # значит молча принять нарушенный формат. Пусть сработает ремонтный повтор.
    if _array_before_object(candidates[0]):
        return None
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    return None


def trace_record(
    prompt: str,
    reply: OllamaReply,
    options: Mapping[str, Any],
    history: Sequence[Mapping[str, str]] | None = None,
    json_valid: bool | None = None,
    name: str = "call",
) -> dict[str, Any]:
    """Собрать запись трейса для одного вызова.

    Запись обязана быть самоописательной: JSONL append-only и общий на тег
    модели, поэтому без `ts` и `call` нельзя сказать, к какому кейсу и к какому
    прогону относится строка. Ровно эта потеря атрибуции и делала замер
    невоспроизводимым (F034, F035).

    Args:
        prompt: Отправленный промпт.
        reply: Ответ модели.
        options: Второй аргумент exec-провайдера.
        history: История переписки (для многоходовых вызовов).
        json_valid: Валиден ли ответ как JSON-объект; `None` — проверить здесь.
        name: Идентификатор вызова (кейс и номер хода) для атрибуции записи.

    Returns:
        Запись с временем, идентификатором вызова, лимитами, фактическими
        счётчиками и признаками усечения.
    """
    config = config_of(options)
    valid = json_valid if json_valid is not None else extract_json_object(reply.text) is not None
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "call": name,
        "model": reply.model,
        "num_ctx": int(_param(config, "num_ctx", DEFAULT_NUM_CTX)),
        "num_predict": int(_param(config, "num_predict", DEFAULT_NUM_PREDICT, "max_tokens")),
        "prompt_chars": len(prompt),
        "history_messages": len(history or []),
        "prompt_eval_count": reply.prompt_eval_count,
        "eval_count": reply.eval_count,
        "done_reason": reply.done_reason,
        "response_chars": len(reply.text),
        "json_valid": valid,
        "context_problems": context_problems(reply, options),
    }


def write_trace(record: Mapping[str, Any], path: Path) -> None:
    """Дописать запись в JSONL-трейс (append-only).

    Args:
        record: Запись вызова.
        path: Путь к JSONL-файлу.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_raw(
    prompt: str,
    reply: OllamaReply,
    options: Mapping[str, Any],
    directory: Path,
    name: str,
) -> Path:
    """Сохранить сырой дамп «промпт + ответ + метаданные».

    Зачем. Замеры волны C («46 КБ → 4096») не воспроизводимы: сырые ответы
    стадий в репозиторий не попали, остался рукописный журнал.

    Args:
        prompt: Отправленный промпт.
        reply: Ответ модели.
        options: Второй аргумент exec-провайдера.
        directory: Каталог дампов.
        name: Базовое имя файла (санитайзится от разделителей пути).

    Returns:
        Путь к записанному файлу.
    """
    safe = "".join(char if char.isalnum() or char in "-_." else "_" for char in name) or "call"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{safe}-{uuid.uuid4().hex[:8]}.json"
    payload = {
        "prompt": prompt,
        "response": reply.text,
        "meta": trace_record(prompt, reply, options),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def record_call(
    prompt: str,
    reply: OllamaReply,
    options: Mapping[str, Any],
    name: str = "call",
    history: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Записать вызов в трейс и сырой дамп, если они включены.

    Args:
        prompt: Отправленный промпт.
        reply: Ответ модели.
        options: Второй аргумент exec-провайдера.
        name: Базовое имя для сырого дампа.
        history: История переписки.

    Returns:
        Запись трейса (пишется на диск только при заданных env-путях).
    """
    record = trace_record(prompt, reply, options, history, name=name)
    trace_path = os.environ.get(TRACE_ENV)
    if trace_path:
        write_trace(record, Path(trace_path))
    raw_dir = os.environ.get(RAW_ENV)
    if raw_dir:
        write_raw(prompt, reply, options, Path(raw_dir), name)
    return record


def ollama_url() -> str:
    """Адрес Ollama на момент вызова (env читается здесь, а не при импорте).

    Returns:
        Базовый URL без завершающего слэша.
    """
    return os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def post_chat(
    body: Mapping[str, Any],
    url: str | None = None,
    timeout: float = 600.0,
) -> dict[str, Any]:
    """Отправить запрос в `/api/chat` и вернуть разобранный ответ.

    Args:
        body: Тело запроса.
        url: Базовый URL Ollama; по умолчанию — `OLLAMA_URL`.
        timeout: Таймаут запроса в секундах.

    Returns:
        JSON-ответ Ollama.

    Raises:
        RuntimeError: Ollama недоступна или ответила ошибкой.
    """
    target = (url or ollama_url()) + "/api/chat"
    request = urllib.request.Request(
        target,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama недоступна на {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Ollama вернула не объект: {type(payload).__name__}")
    return cast(dict[str, Any], payload)


def chat(
    prompt: str,
    options: Mapping[str, Any],
    history: Sequence[Mapping[str, str]] | None = None,
    url: str | None = None,
    timeout: float = 600.0,
) -> OllamaReply:
    """Вызвать Ollama и вернуть текст вместе с метаданными.

    Args:
        prompt: Текст промпта.
        options: Второй аргумент exec-провайдера.
        history: История переписки.
        url: Базовый URL Ollama.
        timeout: Таймаут запроса.

    Returns:
        Ответ модели с метаданными.
    """
    body = build_request(prompt, options, history)
    payload = post_chat(body, url=url, timeout=timeout)
    return parse_reply(payload, str(body["model"]))


def call_guarded(
    prompt: str,
    options: Mapping[str, Any],
    history: Sequence[Mapping[str, str]] | None = None,
    name: str = "call",
) -> OllamaReply:
    """Вызвать модель, записать трейс и проверить, что контекст не усечён.

    Args:
        prompt: Текст промпта.
        options: Второй аргумент exec-провайдера.
        history: История переписки.
        name: Базовое имя для сырого дампа.

    Returns:
        Ответ модели с метаданными.

    Raises:
        ContextTruncatedError: Промпт вытеснен или ответ обрезан.
    """
    reply = chat(prompt, options, history)
    record_call(prompt, reply, options, name=name, history=history)
    enforce_context(reply, options)
    return reply


def call_json(
    prompt: str,
    options: Mapping[str, Any],
    name: str = "call",
) -> tuple[dict[str, Any] | None, OllamaReply]:
    """Вызвать модель и разобрать ответ как JSON-объект роли.

    При невалидном JSON делается **один** ремонтный повтор (отключается
    `ITSF_JSON_RETRY=0`): обрыв формата у 8B-модели не должен превращаться в
    правку артефакта руками (`auto-005`: 4 битых ответа SA из 10).

    Args:
        prompt: Текст промпта.
        options: Второй аргумент exec-провайдера.
        name: Базовое имя для сырого дампа.

    Returns:
        Разобранный объект (или None) и последний ответ модели.
    """
    reply = call_guarded(prompt, options, name=name)
    payload = extract_json_object(reply.text)
    if payload is not None or os.environ.get(JSON_RETRY_ENV) == "0":
        return payload, reply

    retry_reply = call_guarded(prompt + REPAIR_SUFFIX, options, name=f"{name}-retry")
    return extract_json_object(retry_reply.text), retry_reply
