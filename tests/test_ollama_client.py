"""Контракт клиента Ollama: лимиты, метаданные, guard контекста, JSON, трейс.

Зачем. Дефекты волны C («промпт вытеснен», «битый JSON», «замер не
воспроизводим») держались на том, что провайдеры возвращали только текст.
Тесты фиксируют новые инварианты:

- `num_ctx` / `num_predict` попадают в тело запроса из одного места;
- метаданные ответа читаются, а не выбрасываются;
- вытеснение промпта и обрезка ответа падают громко, а не дают артефакт;
- ответ роли обязан быть JSON-объектом, при обрыве — один ремонт;
- трейс и сырой дамп пишутся по env-путям (без них поведение прежнее).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from idea_to_spec import ollama_client as client
from idea_to_spec.ollama_client import (
    DEFAULT_NUM_CTX,
    DEFAULT_NUM_PREDICT,
    ContextTruncatedError,
    OllamaReply,
    build_request,
    call_json,
    context_problems,
    enforce_context,
    extract_json_object,
    parse_reply,
    record_call,
    strip_fences,
)


def _options(**config: object) -> dict[str, object]:
    """Собрать второй аргумент exec-провайдера с заданным config."""
    return {"config": config}


def _reply(
    text: str = "{}", prompt_tokens: int = 10, eval_tokens: int = 5, done: str = "stop"
) -> OllamaReply:
    """Собрать ответ модели для проверок."""
    return OllamaReply(
        text=text,
        model="qwen3:8b",
        prompt_eval_count=prompt_tokens,
        eval_count=eval_tokens,
        done_reason=done,
    )


def test_build_request_pins_context_and_defaults() -> None:
    """Тело запроса содержит num_ctx/num_predict и выключенный think."""
    body = build_request("промпт", _options(model="qwen3:8b", think=False))

    assert body["options"]["num_ctx"] == DEFAULT_NUM_CTX
    assert body["options"]["num_predict"] == DEFAULT_NUM_PREDICT
    assert body["think"] is False
    assert body["messages"] == [{"role": "user", "content": "промпт"}]


def test_build_request_reads_generation_alias() -> None:
    """`max_tokens` из блока generation работает как alias num_predict."""
    body = build_request("п", {"config": {"generation": {"max_tokens": 900}}})

    assert body["options"]["num_predict"] == 900


def test_build_request_puts_history_before_prompt() -> None:
    """История диалога идёт до текущего промпта: модель видит порядок ходов."""
    body = build_request(
        "п",
        _options(),
        history=[{"role": "assistant", "content": "вопрос"}, {"role": "user", "content": "ответ"}],
    )

    assert [message["role"] for message in body["messages"]] == ["assistant", "user", "user"]
    assert body["messages"][-1]["content"] == "п"


def test_json_mode_is_opt_in() -> None:
    """Структурный вывод включается только явным флагом (A/B ещё не проведён)."""
    assert "format" not in build_request("п", _options())
    assert build_request("п", _options(json_mode=True))["format"] == "json"


def test_parse_reply_keeps_metadata() -> None:
    """Счётчики токенов и причина остановки читаются из ответа Ollama."""
    reply = parse_reply(
        {
            "model": "qwen3:8b",
            "message": {"content": "текст"},
            "prompt_eval_count": 4096,
            "eval_count": 600,
            "done_reason": "length",
        }
    )

    assert reply.text == "текст"
    assert reply.prompt_eval_count == 4096
    assert reply.eval_count == 600
    assert reply.done_reason == "length"


def test_parse_reply_tolerates_empty_payload() -> None:
    """Пустой ответ не падает: текст пустой, счётчики нулевые."""
    reply = parse_reply({}, "qwen3:8b")

    assert reply.text == ""
    assert reply.model == "qwen3:8b"
    assert reply.prompt_eval_count == 0
    assert reply.done_reason == ""


def test_context_problems_reports_evicted_prompt() -> None:
    """prompt_eval_count == num_ctx — начало промпта модель не видела."""
    problems = context_problems(_reply(prompt_tokens=DEFAULT_NUM_CTX), _options())

    assert problems and "промпт вытеснен" in problems[0]


def test_context_problems_reports_length_cut() -> None:
    """done_reason=length — ответ обрезан по num_predict."""
    problems = context_problems(_reply(done="length"), _options())

    assert any("ответ обрезан" in problem for problem in problems)


def test_context_problems_reports_overflow_during_generation() -> None:
    """Промпт + ответ больше окна — контекст вытеснялся во время генерации."""
    reply = _reply(prompt_tokens=DEFAULT_NUM_CTX - 10, eval_tokens=100)

    assert any("окно переполнено" in problem for problem in context_problems(reply, _options()))


def test_context_problems_ok_for_normal_reply() -> None:
    """Обычный ответ в пределах окна проблем не даёт."""
    assert context_problems(_reply(), _options()) == []


def test_enforce_context_raises_and_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Усечение падает громко; ITSF_ALLOW_TRUNCATION=1 — для замеров."""
    reply = _reply(prompt_tokens=DEFAULT_NUM_CTX)

    with pytest.raises(ContextTruncatedError, match="промпт вытеснен"):
        enforce_context(reply, _options())

    monkeypatch.setenv("ITSF_ALLOW_TRUNCATION", "1")
    enforce_context(reply, _options())


def test_strip_fences_removes_json_wrapper() -> None:
    """Markdown-обёртка снимается."""
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Вот ответ: {"a": 1} — конец.',
        '\n{"a": 1}\n',
    ],
)
def test_extract_json_object_tolerates_wrapping(text: str) -> None:
    """JSON-объект находится и в обёртке, и в тексте вокруг."""
    assert extract_json_object(text) == {"a": 1}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "не json",
        '{"a": "mit',
        '[{"a": 1}]',
        'Вот ответ: [{"a": 1}]',
        '[1, 2] {"a": 1}',
        '```json\n[{"a": 1}]\n```',
        '{"a": 1,}',
    ],
)
def test_extract_json_object_rejects_broken(text: str) -> None:
    """Битый JSON, массив и не-объект дают None, а не исключение.

    Массив на верхнем уровне — нарушение формата даже с текстом перед ним:
    раньше такой ответ принимался как объект, найденный внутри массива.
    """
    assert extract_json_object(text) is None


def test_extract_json_object_keeps_arrays_inside_object() -> None:
    """Вложенный массив — часть объекта, а не верхний уровень."""
    assert extract_json_object('{"a": [1, 2]}') == {"a": [1, 2]}
    assert extract_json_object('Проза [см. ниже] {"a": 1}') == {"a": 1}


def test_chat_sends_pinned_options_and_parses_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`chat` отправляет num_ctx из config и возвращает метаданные."""
    captured: dict[str, object] = {}

    def fake_post(
        body: dict[str, object], url: str | None = None, timeout: float = 600.0
    ) -> dict[str, object]:
        captured["body"] = body
        return {
            "model": "qwen3:8b",
            "message": {"content": "ok"},
            "prompt_eval_count": 3766,
            "eval_count": 138,
            "done_reason": "stop",
        }

    monkeypatch.setattr(client, "post_chat", fake_post)
    reply = client.chat("п", _options(model="qwen3:8b", num_ctx=16384))

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["options"]["num_ctx"] == 16384
    assert reply.prompt_eval_count == 3766
    assert reply.done_reason == "stop"


def test_record_call_writes_trace_and_raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Трейс и сырой дамп пишутся по env-путям и содержат метаданные."""
    trace = tmp_path / "trace" / "calls.jsonl"
    raw = tmp_path / "raw"
    monkeypatch.setenv("ITSF_TRACE", str(trace))
    monkeypatch.setenv("ITSF_RAW_DIR", str(raw))

    record = record_call("промпт", _reply(text='{"a": 1}'), _options(), name="ORCH-01")

    assert record["json_valid"] is True
    assert record["prompt_chars"] == len("промпт")
    line = json.loads(trace.read_text(encoding="utf-8").splitlines()[0])
    assert line["prompt_eval_count"] == 10
    # Запись атрибутируется: время разбирается, вызов назван кейсом.
    assert line["call"] == "ORCH-01"
    assert datetime.fromisoformat(line["ts"]).tzinfo is not None
    raw_files = list(raw.glob("ORCH-01-*.json"))
    assert raw_files, "сырой дамп не записан"
    dumped = json.loads(raw_files[0].read_text(encoding="utf-8"))
    assert dumped["prompt"] == "промпт"
    assert dumped["response"] == '{"a": 1}'


def test_record_call_is_silent_without_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Без env-путей клиент ничего не пишет: поведение прогона прежнее."""
    monkeypatch.delenv("ITSF_TRACE", raising=False)
    monkeypatch.delenv("ITSF_RAW_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    record_call("п", _reply(), _options(), name="call")

    assert list(tmp_path.iterdir()) == []


def test_call_json_repairs_broken_answer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Битый JSON — один ремонтный повтор, и промпт получает REPAIR_SUFFIX."""
    prompts: list[str] = []
    replies = iter([_reply(text='{"a": "mit'), _reply(text='{"a": 1}')])

    def fake_chat(
        prompt: str,
        options: dict[str, object],
        history: list[dict[str, str]] | None = None,
        url: str | None = None,
        timeout: float = 600.0,
    ) -> OllamaReply:
        prompts.append(prompt)
        return next(replies)

    monkeypatch.delenv("ITSF_JSON_RETRY", raising=False)
    monkeypatch.setattr(client, "chat", fake_chat)
    payload, reply = call_json("промпт", _options(), name="SA")

    assert payload == {"a": 1}
    assert reply.text == '{"a": 1}'
    assert len(prompts) == 2
    assert prompts[1].endswith(client.REPAIR_SUFFIX)


def test_call_json_retry_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ITSF_JSON_RETRY=0 отключает повтор: один вызов, payload=None."""
    prompts: list[str] = []

    def fake_chat(
        prompt: str,
        options: dict[str, object],
        history: list[dict[str, str]] | None = None,
        url: str | None = None,
        timeout: float = 600.0,
    ) -> OllamaReply:
        prompts.append(prompt)
        return _reply(text="не json")

    monkeypatch.setenv("ITSF_JSON_RETRY", "0")
    monkeypatch.setattr(client, "chat", fake_chat)
    payload, reply = call_json("промпт", _options(), name="SA")

    assert payload is None
    assert reply.text == "не json"
    assert len(prompts) == 1
