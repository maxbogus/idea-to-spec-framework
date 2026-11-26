"""Проверка внутренней согласованности прогона `output/<run-id>/`.

Читает артефакты прогона и проверяет структурные инварианты, которые не
ловятся рендером диаграмм и eval ролей:

- каждый `FR-*` ссылается на существующий `BR-*`;
- lifecycle требования корректен, если в таблице есть lifecycle-колонки
  (статус, владелец, риск, версия) — проверки условны, старый формат
  прогонов принимается;
- каждый `FR-*` ссылается хотя бы на один `AC-*` или `NFR-*`;
- каждый `BR-*` покрыт требованием `FR-*` или строкой traceability;
- каждый `J-*` ссылается на существующую персону `P-*`;
- каждый `UC-*` трассируется до `J-*` (в своей строке или в `jtbd.md`);
- узлы диаграмм (`P-/J-/UC-/BR-/FR-/NFR-/R-`) существуют в артефактах;
- traceability-matrix покрывает все `BR-*` и `FR-*`;
- в traceability-matrix у каждого `FR-*` есть задача `T-*` и статус
  покрытия — если матрица в новом формате (P4); старый формат без этих
  колонок принимается, как и в lifecycle-проверках;
- реестр вопросов между этапами (P3): у снятого вопроса есть тема, этап,
  источник и существующие артефакты; повтор темы закрытого вопроса —
  только через `Переоткрывает: Q-n: причина`; `[HYPOTHESIS: Q-n]` при
  закрытом вопросе и ссылка на отсутствующий `Q-n` — дефекты. Старый
  формат без новых колонок проверяется по прежним правилам.

Запуск: `python3 scripts/check_run.py output/auto-002` или
`make check-run RUN=auto-002`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from idea_to_spec.gate_checklists import extract_gate_payloads, validate_gate_payload

#: Регулярки идентификаторов семейств артефактов.
ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "P": re.compile(r"\bP-\d+\b"),
    "J": re.compile(r"\bJ-\d+\b"),
    "UC": re.compile(r"\bUC-\d+\b"),
    "BR": re.compile(r"\bBR-\d+\b"),
    "FR": re.compile(r"\bFR-\d+\b"),
    "NFR": re.compile(r"\bNFR-\d+\b"),
    "R": re.compile(r"\bR-\d+\b"),
}

#: Файл-источник определений для каждого семейства.
ARTIFACT_FILES: dict[str, str] = {
    "P": "personas.md",
    "J": "jtbd.md",
    "UC": "use-cases.md",
    "BR": "business-requirements.md",
    "FR": "functional-requirements.md",
    "NFR": "nonfunctional-requirements.md",
    "R": "risk-register.md",
}

#: Семейства, которые могут встречаться в диаграммах-источниках.
DIAGRAM_FAMILIES: tuple[str, ...] = ("P", "J", "UC", "BR", "FR", "NFR", "R")

#: Допустимые значения статуса требования (жизненный цикл, P1).
VALID_STATUSES: frozenset[str] = frozenset(
    {"draft", "approved", "implemented", "verified", "superseded"}
)
#: Допустимые значения риска требования (P1).
VALID_RISKS: frozenset[str] = frozenset({"low", "medium", "high"})
#: Регулярка идентификатора критерия приёмки.
AC_RE: re.Pattern[str] = re.compile(r"\bAC-\d+\b")
#: Регулярка идентификатора нефункционального требования.
NFR_RE: re.Pattern[str] = re.compile(r"\bNFR-\d+\b")
#: Заголовки lifecycle-колонок в разных вариантах шапки FR-таблицы.
#: Совпадение ищется по нормализованному (без пробелов) виду заголовка.
_STATUS_HEADERS = frozenset({"статус", "status"})
_OWNER_HEADERS = frozenset({"владелец", "owner"})
_RISK_HEADERS = frozenset({"риск", "risk"})
_VERSION_HEADERS = frozenset({"версия", "version"})
#: Заголовки колонки задачи в traceability-матрице (P4, формат «Задача (T-*)»).
_TASK_HEADERS = frozenset({"задача(t-*)", "задача", "task(t-*)", "task", "tasks"})
#: Регулярка идентификатора задачи проекта.
TASK_ID_RE: re.Pattern[str] = re.compile(r"\bT-\d+\b")
#: Заголовки колонки с критерием приёмки в формате BDD.
_BDD_HEADERS = frozenset(
    {
        "критерийприёмки(bdd)",
        "критерийприемки(bdd)",
        "критерийприёмки",
        "acceptancecriteria(bdd)",
        "acceptancecriteria",
    }
)
#: Маркеры формата Given / When / Then в критерии приёмки.
BDD_MARKERS: tuple[str, ...] = ("Given", "When", "Then")
#: Заголовки колонки с мерой и порогом NFR.
_MEASURE_HEADERS = frozenset({"мера/порог", "мера", "порог", "measure", "threshold"})
#: Заголовки колонки с методом проверки NFR.
_METHOD_HEADERS = frozenset({"методпроверки", "какпроверяем", "method"})
#: Заголовки колонки с негативным сценарием приёмки.
_NEGATIVE_AC_HEADERS = frozenset(
    {
        "негативныйсценарий(bdd)",
        "негативныйсценарий",
        "negativeacceptancecriteria",
        "negativeacceptancecriteria(bdd)",
    }
)
#: Стоп-слова, которые делают критерий приёмки непроверяемым.
VAGUE_WORDS: tuple[str, ...] = (
    "быстро",
    "удобно",
    "правильно",
    "качественно",
    "эффективно",
    "надёжно",
)
#: Заголовки колонки статуса ADR.
_ADR_STATUS_HEADERS = frozenset({"статус", "status"})
#: Заголовки колонки рассмотренных альтернатив ADR.
_ADR_ALT_HEADERS = frozenset(
    {
        "рассмотренныеальтернативы(pros/cons)",
        "рассмотренныеальтернативы",
        "альтернативы",
        "alternatives",
    }
)
#: Заголовки колонки последствий ADR.
_ADR_CONS_HEADERS = frozenset({"последствия", "consequences"})
#: Допустимые статусы ADR.
VALID_ADR_STATUSES = frozenset({"proposed", "accepted", "deprecated", "superseded"})
#: Признаки того, что требование затрагивает персональные данные.
PDN_MARKERS: tuple[str, ...] = (
    "персональн",
    "ПДн",
    "фИО",
    "данные клиент",
    "данные пользовател",
    "e-mail",
    "email",
    "телефон",
)
#: Маркеры незаполненного шаблона раздела spec.md §6.
EMPTY_SECTION_MARKERS: tuple[str, ...] = ("Какие данные, персональные ли", "перечислить таблицы")


def _normalize_header(text: str) -> str:
    """Нормализовать заголовок колонки: нижний регистр, без пробелов.

    Args:
        text: Исходный заголовок.

    Returns:
        Нормализованный заголовок.
    """
    return text.strip().lower().replace(" ", "")


def _column_index(header: list[str], names: frozenset[str]) -> int | None:
    """Найти индекс колонки по одному из возможных заголовков.

    Args:
        header: Ячейки строки-шапки.
        names: Множество допустимых нормализованных заголовков.

    Returns:
        Индекс колонки или ``None``, если такой колонки нет.
    """
    for index, cell in enumerate(header):
        if _normalize_header(cell) in names:
            return index
    return None


def _find_header(rows: list[list[str]]) -> list[str] | None:
    """Найти строку-шапку таблицы требований.

    Args:
        rows: Разобранные строки таблиц.

    Returns:
        Ячейки шапки или ``None``, если шапка не найдена.
    """
    for cells in rows:
        if not cells:
            continue
        first = _normalize_header(cells[0])
        if first in {"id", "ид"}:
            return cells
    return None


def _matrix_header(rows: list[list[str]]) -> list[str] | None:
    """Найти строку-шапку traceability-матрицы.

    В матрице первая колонка — бизнес-цель, а не `ID`, поэтому `_find_header`
    её не находит. Шапка опознаётся по колонке «Требование».

    Args:
        rows: Разобранные строки таблиц.

    Returns:
        Ячейки шапки или ``None``, если матрица не найдена.
    """
    for cells in rows:
        if not cells:
            continue
        normalized = [_normalize_header(cell) for cell in cells]
        if "требование" in normalized or "requirement" in normalized:
            return cells
    return None


def _read(path: Path) -> str:
    """Прочитать файл в UTF-8 (пустая строка, если файла нет).

    Args:
        path: Путь к файлу.

    Returns:
        Содержимое файла или пустая строка.
    """
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _defined(text: str, family: str) -> set[str]:
    """Собрать все ID семейства, встречающиеся в тексте.

    Args:
        text: Текст артефакта.
        family: Семейство идентификаторов (P, J, UC, BR, ...).

    Returns:
        Множество найденных ID.
    """
    return set(ID_PATTERNS[family].findall(text))


def _rows(text: str) -> list[list[str]]:
    """Разобрать markdown-таблицы в список строк ячеек.

    Args:
        text: Текст артефакта.

    Returns:
        Список строк таблиц; каждая строка — список ячеек.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows


def _check_fr_sources(text: str, br_defined: set[str], problems: list[str]) -> None:
    """Каждый FR-* ссылается на существующий BR-*."""
    for cells in _rows(text):
        if not cells:
            continue
        match = re.match(r"FR-\d+", cells[0])
        if match is None:
            continue
        fr = match.group(0)
        refs = ID_PATTERNS["BR"].findall(" | ".join(cells))
        if not refs:
            problems.append(f"{fr}: нет источника BR-* в functional-requirements.md")
            continue
        for ref in refs:
            if ref not in br_defined:
                problems.append(f"{fr}: источник {ref} не определён в business-requirements.md")


def _check_fr_lifecycle(text: str, problems: list[str]) -> None:
    """Проверить lifecycle-поля требования: статус, владелец, риск, версия.

    Проверки условны: если в шапке таблицы нет lifecycle-колонок (старый
    формат прогонов), они пропускаются. Это позволяет менять формат
    постепенно, не ломая уже записанные прогоны.

    Args:
        text: Текст `functional-requirements.md`.
        problems: Список накопленных проблем (дополняется на месте).
    """
    rows = _rows(text)
    header = _find_header(rows)
    if header is None:
        return
    status_at = _column_index(header, _STATUS_HEADERS)
    owner_at = _column_index(header, _OWNER_HEADERS)
    risk_at = _column_index(header, _RISK_HEADERS)
    version_at = _column_index(header, _VERSION_HEADERS)
    bdd_at = _column_index(header, _BDD_HEADERS)
    if status_at is None and owner_at is None and risk_at is None and version_at is None:
        return

    for cells in rows:
        if not cells:
            continue
        match = re.match(r"FR-\d+", cells[0])
        if match is None:
            continue
        fr = match.group(0)
        risk = ""
        if risk_at is not None and risk_at < len(cells):
            risk = cells[risk_at].strip().lower()

        if status_at is not None and status_at < len(cells):
            status = cells[status_at].strip().lower()
            if status and status not in VALID_STATUSES:
                allowed = ", ".join(sorted(VALID_STATUSES))
                problems.append(f"{fr}: недопустимый статус «{status}» (допустимо: {allowed})")

        if owner_at is not None and owner_at < len(cells) and not cells[owner_at].strip():
            problems.append(f"{fr}: не указан владелец (требование не готово по DoR)")

        if risk_at is not None and risk_at < len(cells):
            if risk and risk not in VALID_RISKS:
                allowed = ", ".join(sorted(VALID_RISKS))
                problems.append(f"{fr}: недопустимый риск «{risk}» (допустимо: {allowed})")
            elif risk == "high" and not AC_RE.search(" | ".join(cells)):
                problems.append(f"{fr}: высокий риск, но не указан критерий приёмки (AC-*)")

        if version_at is not None and version_at < len(cells):
            version = cells[version_at].strip()
            if version and not version.isdigit():
                problems.append(f"{fr}: версия «{version}» не является целым числом")

        if bdd_at is not None and bdd_at < len(cells) and risk == "high":
            criteria = cells[bdd_at]
            missing = [marker for marker in BDD_MARKERS if marker not in criteria]
            if missing:
                problems.append(
                    f"{fr}: высокий риск, но критерий приёмки не в формате BDD "
                    f"(нет маркеров: {', '.join(missing)})"
                )


def _check_fr_criteria(text: str, problems: list[str]) -> None:
    """Каждое FR-* ссылается хотя бы на один критерий приёмки (AC) или NFR.

    Требование без критерия проверки нечем принять — это нарушение DoR.

    Args:
        text: Текст `functional-requirements.md`.
        problems: Список накопленных проблем (дополняется на месте).
    """
    for cells in _rows(text):
        if not cells:
            continue
        match = re.match(r"FR-\d+", cells[0])
        if match is None:
            continue
        fr = match.group(0)
        joined = " | ".join(cells)
        if not (AC_RE.search(joined) or NFR_RE.search(joined)):
            problems.append(f"{fr}: нет критерия приёмки (AC-*) и нет ссылки на NFR-*")


def _check_br_coverage(fr_text: str, br_text: str, trac_text: str, problems: list[str]) -> None:
    """Каждое BR-* покрыто требованием FR-* или строкой traceability.

    Бизнес-требование может быть нефункциональным по природе (тогда его
    закрывает NFR, а BR-* попадает в traceability отдельной строкой) — это
    легитимный путь покрытия.

    Args:
        fr_text: Текст `functional-requirements.md`.
        br_text: Текст `business-requirements.md`.
        trac_text: Текст `traceability-matrix.md`.
        problems: Список накопленных проблем (дополняется на месте).
    """
    covered: set[str] = set()
    for cells in _rows(fr_text):
        if not cells:
            continue
        if re.match(r"FR-\d+", cells[0]) is None:
            continue
        covered |= set(ID_PATTERNS["BR"].findall(" | ".join(cells)))

    for cells in _rows(br_text):
        if not cells:
            continue
        match = re.match(r"BR-\d+", cells[0])
        if match is None:
            continue
        br = match.group(0)
        if br in covered:
            continue
        if br in trac_text:
            continue
        problems.append(f"{br}: не покрыт ни одним FR-* и не отражён в traceability-matrix.md")


def _check_j_persons(text: str, p_defined: set[str], problems: list[str]) -> None:
    """Каждый J-* ссылается на существующую персону P-*."""
    for cells in _rows(text):
        if not cells:
            continue
        match = re.match(r"J-\d+", cells[0])
        if match is None:
            continue
        j = match.group(0)
        refs = ID_PATTERNS["P"].findall(" | ".join(cells))
        if not refs:
            problems.append(f"{j}: нет ссылки на персону P-* в jtbd.md")
            continue
        for ref in refs:
            if ref not in p_defined:
                problems.append(f"{j}: персона {ref} не определена в personas.md")


def _check_uc_trace(uc_text: str, jtbd_text: str, j_defined: set[str], problems: list[str]) -> None:
    """Каждый UC-* трассируется до J-* (в строке UC или в jtbd.md)."""
    for cells in _rows(uc_text):
        if not cells:
            continue
        match = re.match(r"UC-\d+", cells[0])
        if match is None:
            continue
        uc = match.group(0)
        refs = ID_PATTERNS["J"].findall(" | ".join(cells))
        if not refs:
            if uc not in jtbd_text:
                problems.append(f"{uc}: не трассируется до J-* (ни в use-cases.md, ни в jtbd.md)")
            continue
        for ref in refs:
            if ref not in j_defined:
                problems.append(f"{uc}: трассируется в {ref}, которого нет в jtbd.md")


def _check_diagrams(diagrams: Path, defined: dict[str, set[str]], problems: list[str]) -> None:
    """Узлы диаграмм ссылаются только на определённые ID."""
    if not diagrams.is_dir():
        return
    for path in sorted(diagrams.glob("*.mmd")):
        text = path.read_text(encoding="utf-8")
        for family in DIAGRAM_FAMILIES:
            for ref in ID_PATTERNS[family].findall(text):
                if ref not in defined[family]:
                    problems.append(f"{path.name}: узел {ref} не найден в {ARTIFACT_FILES[family]}")


def _check_traceability(trac_text: str, defined: dict[str, set[str]], problems: list[str]) -> None:
    """Traceability-matrix покрывает все BR-* и FR-*."""
    if not trac_text.strip():
        problems.append("traceability-matrix.md отсутствует или пуст")
        return
    for family in ("BR", "FR"):
        for ref in sorted(defined[family]):
            if ref not in trac_text:
                problems.append(f"{ref}: не покрыт в traceability-matrix.md")


def _check_task_traceability(
    trac_text: str, fr_defined: set[str], problems: list[str]
) -> None:
    """Каждое требование привязано к задаче `T-*` и имеет статус покрытия (P4).

    Зачем. Матрица без задач отвечает «зачем требование», но не «кто его
    делает и в каком оно состоянии»: `FR-*` мог быть покрыт строкой, где нет
    ни задачи, ни статуса, и прогон проходил гейт. Теперь такая строка —
    проблема.

    Проверка условна по формату: если в шапке матрицы нет колонки задачи
    (демо-прогоны 2026-11), она пропускается — тот же приём, что у
    lifecycle-колонок в `_check_fr_lifecycle`.

    Колонка «Коммит / тест» не обязательна: на этапе плана коммита ещё нет,
    а статус покрытия проверяем уже на планировании.

    Args:
        trac_text: Текст `traceability-matrix.md`.
        fr_defined: Идентификаторы `FR-*`, определённые в требованиях.
        problems: Список накопленных проблем (дополняется на месте).
    """
    rows = _rows(trac_text)
    header = _matrix_header(rows)
    if header is None:
        return
    task_at = _column_index(header, _TASK_HEADERS)
    if task_at is None:
        return
    status_at = _column_index(header, _STATUS_HEADERS)
    if status_at is None:
        problems.append(
            "traceability-matrix.md: есть колонка задачи (T-*), но нет колонки "
            "«Статус» — состояние покрытия требования не проверить"
        )
        return

    covered: set[str] = set()
    for cells in rows:
        if not cells or cells is header:
            continue
        refs = list(dict.fromkeys(ID_PATTERNS["FR"].findall(" | ".join(cells))))
        if not refs:
            continue
        task = cells[task_at].strip() if task_at < len(cells) else ""
        status = cells[status_at].strip().lower() if status_at < len(cells) else ""
        for fr in refs:
            covered.add(fr)
            if TASK_ID_RE.search(task) is None:
                problems.append(
                    f"{fr}: в traceability-matrix.md нет задачи (T-*) — "
                    "требование не привязано к работе"
                )
            if not status:
                problems.append(f"{fr}: в traceability-matrix.md не указан статус покрытия")
            elif status not in VALID_STATUSES:
                allowed = ", ".join(sorted(VALID_STATUSES))
                problems.append(
                    f"{fr}: недопустимый статус «{status}» в traceability-matrix.md "
                    f"(допустимо: {allowed})"
                )

    for fr in sorted(fr_defined & set(ID_PATTERNS["FR"].findall(trac_text))):
        if fr not in covered:
            problems.append(
                f"{fr}: упомянут в traceability-matrix.md без строки с задачей (T-*) и статусом"
            )


#: Статус закрытого вопроса: ответ получен, источник указан.
CLOSED_STATUS = "закрыт"
#: Статус открытого вопроса: ответа нет.
OPEN_STATUS = "открыт"
#: Статус допущения: вопрос снят временным предположением, а не ответом.
ASSUMPTION_STATUS = "допущение"
#: Маркер источника ответа заказчика.
CUSTOMER_ANSWER_MARKER = "ответ заказчика"
#: Регулярка идентификатора вопроса в таблице открытых вопросов.
QUESTION_ID_RE: re.Pattern[str] = re.compile(r"\bQ-\d+\b")

#: Этапы, на которых вопрос может быть снят (значения поля `stage` из
#: `prompts/orchestrator.md` без гейтов и служебного `done`).
#: Согласованность закреплена тестом `test_registry_stage_enum_matches_orchestrator`.
QUESTION_STAGES: frozenset[str] = frozenset(
    {
        "intake",
        "business",
        "design_sketch",
        "system",
        "architecture",
        "validation",
        "plan",
        "design_cjm",
    }
)

#: Значения, которыми нельзя закрыть вопрос: причина или источник не названы.
_EMPTY_VALUES = frozenset({"", "-", "—", "–", "нет", "н/д", "n/a", "na", "none"})

#: Заголовки колонок реестра → ключи строки (`_normalize_question_header`).
_QUESTION_COLUMNS: dict[str, str] = {
    "id": "id",
    "тема": "topic",
    "вопрос": "question",
    "почемублокирует": "why",
    "почемубылбыблокером": "why",
    "ктоотвечает": "owner",
    "статус": "status",
    "закрытнаэтапе": "stage",
    "источникответа": "source",
    "ответ(источник)": "source",
    "чтообновлено": "artifacts",
    "переоткрывает": "reopens",
}

#: Артефакты, в которых проверяются ссылки на вопросы и маркеры гипотез.
#: `validation-report.md`, `hallucination-log.md` и `run-report.md` исключены:
#: там `[HYPOTHESIS: Q-n]` — цитата находки, а не живая помета.
_QUESTION_ARTIFACTS: tuple[str, ...] = (
    "brief.md",
    "personas.md",
    "jtbd.md",
    "business-requirements.md",
    "functional-requirements.md",
    "nonfunctional-requirements.md",
    "use-cases.md",
    "spec.md",
    "cjm.md",
    "risk-register.md",
    "human-oversight-plan.md",
    "traceability-matrix.md",
)

#: Ссылка на артефакт в ячейке реестра.
_ARTIFACT_FILE_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9_.-]+\.(?:md|mmd|bpmn)")
#: Ссылка на раздел артефакта (`spec.md §9`).
_SECTION_REF_RE: re.Pattern[str] = re.compile(r"([A-Za-z0-9_.-]+\.md)\s*§\s*(\d+)")
#: Живая помета допущения в артефакте.
_HYPOTHESIS_MARKER_RE: re.Pattern[str] = re.compile(
    r"\[HYPOTHESIS:\s*(Q-\d+)\]", re.IGNORECASE
)
#: Ссылка на переоткрытый вопрос: `Q-n: причина`.
_REOPEN_RE: re.Pattern[str] = re.compile(r"^(Q-\d+)\s*[:—–-]\s*(.+)$")


def _normalize_question_header(cell: str) -> str:
    """Привести заголовок колонки реестра к сравнимому виду.

    Args:
        cell: Текст ячейки шапки таблицы.

    Returns:
        Заголовок без пробелов, звёздочек и backticks, в нижнем регистре.
    """
    return re.sub(r"[\s*`]+", "", cell.strip().lower())


def _is_empty(value: str) -> bool:
    """Проверить, что значение — пустышка, а не содержательный текст.

    Args:
        value: Текст ячейки.

    Returns:
        True, если ячейка пуста или заполнена заглушкой (`—`, `нет`, `н/д`).
    """
    return value.strip().strip("`").lower() in _EMPTY_VALUES


def _status_kind(value: str) -> str:
    """Определить статус вопроса по значению ячейки.

    Args:
        value: Значение колонки «Статус».

    Returns:
        `закрыт`, `допущение`, `открыт` или пустая строка, если статус неизвестен.
    """
    lowered = value.strip().lower()
    for kind in (CLOSED_STATUS, ASSUMPTION_STATUS, OPEN_STATUS):
        if lowered.startswith(kind):
            return kind
    return ""


def _question_tables(text: str) -> list[tuple[dict[str, int], list[dict[str, str]]]]:
    """Разобрать таблицы вопросов по именам колонок.

    Позиционный разбор («первая и последняя ячейки») ломался, как только
    после «Статуса» появлялась новая колонка. Здесь колонка ищется по шапке:
    старые прогоны (`ID | Вопрос | Ответ (источник) | Статус`) и новые
    (`ID | Тема | ... | Переоткрывает`) разбираются одинаково.

    Args:
        text: Текст файла `open-questions.md`.

    Returns:
        Список пар «карта колонок» и «строки таблицы».
    """
    tables: list[tuple[dict[str, int], list[dict[str, str]]]] = []
    header: dict[str, int] | None = None
    rows: list[dict[str, str]] = []

    for line in text.splitlines():
        if not line.strip().startswith("|"):
            if header is not None:
                tables.append((header, rows))
            header, rows = None, []
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        normalized = [_normalize_question_header(cell) for cell in cells]
        if "id" in normalized and "статус" in normalized:
            if header is not None:
                tables.append((header, rows))
            header = {}
            for index, cell in enumerate(normalized):
                key = _QUESTION_COLUMNS.get(cell)
                if key is not None and key not in header:
                    header[key] = index
            rows = []
            continue
        if header is None:
            continue
        match = QUESTION_ID_RE.search(cells[0])
        if match is None:
            continue
        row = {"id": match.group(0), "_raw": " | ".join(cells)}
        for key, index in header.items():
            row[key] = cells[index] if index < len(cells) else ""
        rows.append(row)

    if header is not None:
        tables.append((header, rows))
    return tables


def _artifact_exists(run_dir: Path, name: str) -> bool:
    """Проверить, что артефакт прогона существует.

    Args:
        run_dir: Каталог прогона.
        name: Имя файла из ячейки реестра.

    Returns:
        True, если файл есть в прогоне или в `diagrams/`.
    """
    return (run_dir / name).is_file() or (run_dir / "diagrams" / name).is_file()


def _check_question_artifacts(
    question_id: str, cell: str, run_dir: Path, problems: list[str]
) -> None:
    """Проверить колонку «Что обновлено».

    Ответ, не дошедший до артефакта, — это закрытый на бумаге вопрос: именно
    так в chat-002 ответ про контур остался допущением в другой строке.

    Args:
        question_id: Идентификатор вопроса.
        cell: Значение колонки.
        run_dir: Каталог прогона.
        problems: Список проблем (дополняется на месте).
    """
    if _is_empty(cell):
        problems.append(
            f"{question_id}: не указано, что обновлено, — ответ не дошёл до артефактов"
        )
        return
    files = _ARTIFACT_FILE_RE.findall(cell)
    if not files:
        problems.append(f"{question_id}: в «Что обновлено» не назван ни один файл артефакта")
        return
    for name in files:
        if not _artifact_exists(run_dir, name):
            problems.append(
                f"{question_id}: артефакт {name} из «Что обновлено» не найден в прогоне"
            )


def _check_question_source(
    question_id: str, source: str, run_dir: Path, problems: list[str]
) -> None:
    """Проверить, что источник ответа существует, если он назван файлом.

    Args:
        question_id: Идентификатор вопроса.
        source: Значение колонки «Источник ответа».
        run_dir: Каталог прогона.
        problems: Список проблем (дополняется на месте).
    """
    for name in _ARTIFACT_FILE_RE.findall(source):
        if not _artifact_exists(run_dir, name):
            problems.append(f"{question_id}: источник ответа {name} не найден в прогоне")
    for name, number in _SECTION_REF_RE.findall(source):
        path = run_dir / name
        if path.is_file() and _section(path.read_text(encoding="utf-8"), number) is None:
            problems.append(f"{question_id}: источника {name} §{number} нет в прогоне")


def _check_legacy_row(row: dict[str, str], problems: list[str]) -> None:
    """Проверить строку старого формата (без темы и этапа).

    Args:
        row: Разобранная строка таблицы.
        problems: Список проблем (дополняется на месте).
    """
    question_id = row["id"]
    status = row.get("status", "").strip().lower()
    has_source = CUSTOMER_ANSWER_MARKER in row.get("_raw", "").lower()
    if status == CLOSED_STATUS and not has_source:
        problems.append(
            f"{question_id}: статус «{CLOSED_STATUS}», но источник ответа "
            "не указан — непонятно, на чём основан ответ"
        )
    if status == OPEN_STATUS and has_source:
        problems.append(
            f"{question_id}: статус «{OPEN_STATUS}», но источник ответа "
            "указан — вопрос помечен открытым, хотя ответ есть"
        )


def _check_registry_row(row: dict[str, str], run_dir: Path, problems: list[str]) -> None:
    """Проверить строку реестра P3.

    Args:
        row: Разобранная строка таблицы.
        run_dir: Каталог прогона (для проверки артефактов и источников).
        problems: Список проблем (дополняется на месте).
    """
    question_id = row["id"]
    status_value = row.get("status", "").strip()
    status = _status_kind(status_value)
    if not status:
        problems.append(
            f"{question_id}: неизвестный статус «{status_value}» в реестре "
            f"(допустимо: {CLOSED_STATUS}, {ASSUMPTION_STATUS}, {OPEN_STATUS})"
        )
        return

    topic = row.get("topic", "").strip()
    if _is_empty(topic):
        problems.append(
            f"{question_id}: не указана тема — повтор вопроса между этапами не проверить"
        )

    stage = row.get("stage", "").strip().lower()
    source = row.get("source", "").strip()
    artifacts = row.get("artifacts", "").strip()

    if status == OPEN_STATUS:
        if not _is_empty(source):
            problems.append(
                f"{question_id}: статус «{OPEN_STATUS}», но источник ответа указан — "
                "вопрос помечен открытым, хотя ответ есть"
            )
        if not _is_empty(stage):
            problems.append(
                f"{question_id}: статус «{OPEN_STATUS}», но указан этап закрытия «{stage}»"
            )
        return

    if _is_empty(stage):
        problems.append(
            f"{question_id}: не указан этап, на котором вопрос снят (Закрыт на этапе)"
        )
    elif stage not in QUESTION_STAGES:
        allowed = ", ".join(sorted(QUESTION_STAGES))
        problems.append(
            f"{question_id}: недопустимый этап «{stage}» (допустимо: {allowed})"
        )

    _check_question_artifacts(question_id, artifacts, run_dir, problems)
    if status == CLOSED_STATUS:
        if _is_empty(source):
            problems.append(
                f"{question_id}: статус «{CLOSED_STATUS}», но источник ответа "
                "не указан — непонятно, на чём основан ответ"
            )
        else:
            _check_question_source(question_id, source, run_dir, problems)


def _check_registry_cross(rows: list[dict[str, str]], problems: list[str]) -> None:
    """Проверить связи между строками реестра.

    Правило: тема закрытого вопроса не возвращается как открытая или как
    допущение без ссылки `Переоткрывает: Q-n: причина`. Это и есть реестр
    между этапами — следующий этап видит, что уже отвечено.

    Args:
        rows: Все строки всех таблиц файла.
        problems: Список проблем (дополняется на месте).
    """
    by_id = {row["id"]: row for row in rows}
    closed_topics: dict[str, list[str]] = {}
    for row in rows:
        if not row.get("question", "").strip():
            continue
        if _status_kind(row.get("status", "")) != CLOSED_STATUS:
            continue
        topic = row.get("topic", "").strip().lower()
        if topic:
            closed_topics.setdefault(topic, []).append(row["id"])

    for row in rows:
        question_id = row["id"]
        if not row.get("question", "").strip():
            continue

        target = ""
        reopens = row.get("reopens", "").strip()
        if not _is_empty(reopens):
            match = _REOPEN_RE.match(reopens)
            if match is None:
                problems.append(
                    f"{question_id}: «Переоткрывает» в формате «Q-n: причина» "
                    f"(получено: {reopens!r})"
                )
            else:
                target, reason = match.group(1), match.group(2).strip()
                target_row = by_id.get(target)
                if target_row is None:
                    problems.append(
                        f"{question_id}: «Переоткрывает» ссылается на {target}, "
                        "которого нет в реестре"
                    )
                elif _status_kind(target_row.get("status", "")) != CLOSED_STATUS:
                    problems.append(
                        f"{question_id}: «Переоткрывает» ссылается на {target}, "
                        "но он не закрыт — переоткрывать нечего"
                    )
                if _is_empty(reason):
                    problems.append(f"{question_id}: переоткрытие без причины")

        if _status_kind(row.get("status", "")) == CLOSED_STATUS:
            continue
        topic = row.get("topic", "").strip().lower()
        if not topic:
            continue
        closed = closed_topics.get(topic, [])
        if not closed or (target and target in closed):
            continue
        problems.append(
            f"{question_id}: тема «{topic}» уже закрыта в {closed[0]} — повтор без "
            "«Переоткрывает: Q-n: причина»"
        )


def _check_question_references(
    rows: list[dict[str, str]],
    registry_rows: list[dict[str, str]],
    run_dir: Path,
    problems: list[str],
) -> None:
    """Проверить ссылки артефактов на реестр.

    Два дефекта: (1) вопрос закрыт, а артефакт всё ещё помечает его как
    гипотезу — ответ не перенесён; (2) артефакт ссылается на вопрос, которого
    в реестре нет, — строку удалили, трассировка порвалась.

    Args:
        rows: Все строки реестра.
        run_dir: Каталог прогона.
        problems: Список проблем (дополняется на месте).
    """
    known = {row["id"] for row in rows}
    # Маркеры проверяются только для закрытых вопросов реестра: старый формат
    # не знал этапа и мог держать пометку `[HYPOTHESIS: Q-n]` у закрытого
    # вопроса — его поведение не меняем.
    closed = {
        row["id"]
        for row in registry_rows
        if row.get("question", "").strip()
        and _status_kind(row.get("status", "")) == CLOSED_STATUS
    }
    for name in _QUESTION_ARTIFACTS:
        path = run_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for question_id in _HYPOTHESIS_MARKER_RE.findall(text):
            question_id = question_id.upper()
            if question_id in closed:
                problems.append(
                    f"{name}: {question_id} закрыт, но артефакт всё ещё помечает его "
                    "как [HYPOTHESIS] — ответ не перенесён в требование"
                )
        for question_id in QUESTION_ID_RE.findall(text):
            question_id = question_id.upper()
            if question_id not in known:
                problems.append(
                    f"{name}: ссылка на {question_id}, которого нет в реестре "
                    "open-questions.md"
                )


def _check_open_questions(text: str, problems: list[str], run_dir: Path) -> None:
    """Проверить реестр вопросов и его связи с артефактами.

    Старый формат (без колонок «Тема» и «Закрыт на этапе») проверяется по
    прежним правилам: исторические прогоны не должны краснеть из-за контракта,
    которого в них не было. Новый формат проверяется полностью: тема, этап,
    источник, обновлённые артефакты, переоткрытие и живые пометы гипотез.

    Args:
        text: Текст файла `open-questions.md`.
        problems: Список накопленных проблем (дополняется на месте).
        run_dir: Каталог прогона (для проверки артефактов).
    """
    if not text.strip():
        return

    tables = _question_tables(text)
    rows = [row for _, table_rows in tables for row in table_rows]
    if not rows:
        return

    seen: set[str] = set()
    for row in rows:
        question_id = row["id"]
        if question_id in seen:
            problems.append(f"{question_id}: вопрос повторяется в open-questions.md")
        seen.add(question_id)

    registry_rows: list[dict[str, str]] = []
    for header, table_rows in tables:
        is_registry = "topic" in header and "stage" in header
        for row in table_rows:
            # Пустая шаблонная строка — не вопрос: шаблон не обязан быть заполнен.
            if not row.get("question", "").strip():
                continue
            if is_registry:
                registry_rows.append(row)
                _check_registry_row(row, run_dir, problems)
            else:
                _check_legacy_row(row, problems)

    if registry_rows:
        _check_registry_cross(rows, problems)
        _check_question_references(rows, registry_rows, run_dir, problems)


def _section(text: str, number: str) -> str | None:
    """Извлечь раздел markdown по его номеру заголовка.

    Args:
        text: Текст документа.
        number: Номер раздела (например, `6`).

    Returns:
        Содержимое раздела или ``None``, если раздела нет.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(number)}\.\s.*?$(.*?)(?=^##\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def _check_pdn_section(fr_text: str, spec_text: str, problems: list[str]) -> None:
    """Если требование затрагивает ПДн, раздел spec.md §6 должен быть заполнен.

    Персональные данные без раздела «Данные и безопасность» — это
    требование, о котором нельзя сказать, где оно лежит и когда
    удаляется. Проверка условна: если раздела нет вовсе, проблема тоже
    фиксируется (значит, его не заполнили).

    Args:
        fr_text: Текст `functional-requirements.md`.
        spec_text: Текст `spec.md`.
        problems: Список накопленных проблем (дополняется на месте).
    """
    touched: list[str] = []
    for cells in _rows(fr_text):
        if not cells:
            continue
        match = re.match(r"FR-\d+", cells[0])
        if match is None:
            continue
        if any(marker in " | ".join(cells) for marker in PDN_MARKERS):
            touched.append(match.group(0))
    if not touched:
        return

    section = _section(spec_text, "6")
    if section is None:
        problems.append(
            f"{touched[0]}: затрагивает персональные данные, но раздел "
            "«Данные и безопасность» (spec.md §6) отсутствует"
        )
        return
    if any(marker in section for marker in EMPTY_SECTION_MARKERS):
        problems.append(
            f"{touched[0]}: затрагивает персональные данные, но spec.md §6 "
            "не заполнен (классификация, data residency, срок хранения)"
        )


def _check_nfr_measurability(text: str, problems: list[str]) -> bool:
    """Проверить NFR с мерой и методом, если колонки есть в шапке.

    Returns:
        True, если проверка применилась (колонка меры найдена).
    """

    rows = _rows(text)
    header = _find_header(rows)
    if header is None:
        return False
    measure_at = _column_index(header, _MEASURE_HEADERS)
    if measure_at is None:
        return False
    method_at = _column_index(header, _METHOD_HEADERS)

    for cells in rows:
        if not cells or cells is header:
            continue
        match = re.match(r"NFR-\d+", cells[0])
        if match is None:
            continue
        nfr = match.group(0)
        measure = cells[measure_at].strip() if measure_at < len(cells) else ""
        if not measure:
            problems.append(f"{nfr}: не указана мера/порог (колонка «Мера / Порог»)")
        if method_at is not None:
            method = cells[method_at].strip() if method_at < len(cells) else ""
            if not method:
                problems.append(f"{nfr}: не указан метод проверки")
    return True


def _check_negative_acceptance(text: str, problems: list[str]) -> None:
    """Проверить негативный AC и стоп-слова, если колонки есть в шапке."""

    rows = _rows(text)
    header = _find_header(rows)
    if header is None:
        return
    negative_at = _column_index(header, _NEGATIVE_AC_HEADERS)
    if negative_at is None:
        return
    bdd_at = _column_index(header, _BDD_HEADERS)

    for cells in rows:
        if not cells or cells is header:
            continue
        match = re.match(r"FR-\d+", cells[0])
        if match is None:
            continue
        fr = match.group(0)
        negative = cells[negative_at] if negative_at < len(cells) else ""
        if AC_RE.search(negative) is None:
            problems.append(f"{fr}: нет негативного критерия приёмки (AC-*)")
        for index in (bdd_at, negative_at):
            if index is None or index >= len(cells):
                continue
            lowered = cells[index].lower()
            for word in VAGUE_WORDS:
                if word in lowered:
                    problems.append(f"{fr}: критерий приёмки содержит стоп-слово «{word}»")


def _alternative_count(cell: str) -> int:
    """Посчитать альтернативы в ячейке ADR."""

    parts = re.split(r"<br\s*/?>|\n|;", cell)
    return len([part for part in parts if part.strip()])


def _check_adr(spec_text: str, problems: list[str]) -> None:
    """Проверить ADR с статусом, альтернативами и последствиями (условно)."""

    section = _section(spec_text, "10")
    if section is None:
        return
    rows = _rows(section)
    header = _find_header(rows)
    if header is None:
        return
    status_at = _column_index(header, _ADR_STATUS_HEADERS)
    if status_at is None:
        return
    alternatives_at = _column_index(header, _ADR_ALT_HEADERS)
    if alternatives_at is None:
        problems.append("spec.md §10: нет колонки «Рассмотренные альтернативы»")
        return
    consequences_at = _column_index(header, _ADR_CONS_HEADERS)

    for cells in rows:
        if not cells or cells is header:
            continue
        match = re.match(r"ADR-\d+", cells[0])
        if match is None:
            continue
        adr = match.group(0)
        status = cells[status_at].strip() if status_at < len(cells) else ""
        if status.lower() not in VALID_ADR_STATUSES:
            allowed = ", ".join(sorted(VALID_ADR_STATUSES))
            problems.append(
                f"{adr}: недопустимый статус ADR «{status}» (допустимо: {allowed})"
            )
        alternatives = cells[alternatives_at] if alternatives_at < len(cells) else ""
        if _alternative_count(alternatives) < 2:
            problems.append(f"{adr}: меньше двух рассмотренных альтернатив")
        consequences = cells[consequences_at] if consequences_at is not None and consequences_at < len(cells) else ""
        if not consequences.strip():
            problems.append(f"{adr}: не указаны последствия решения")


def _check_gate_reports(text: str, problems: list[str]) -> None:
    """Проверить ответы гейтов из раздела «Гейты» в validation-report.md.

    Проверка условна, как lifecycle-колонки: старые прогоны раздела не имеют
    и принимаются. Если раздел есть, вердикт гейта обязан быть машинно-читаемым
    (`checks[]`): гейт-печать «passed при незакрытых пунктах» — дефект волны C,
    и он ловится здесь, а не глазами.

    Args:
        text: Содержимое `validation-report.md`.
        problems: Список проблем, куда дописываются находки.
    """
    payloads, parse_problems = extract_gate_payloads(text)
    problems.extend(f"validation-report.md: {problem}" for problem in parse_problems)
    for payload in payloads:
        for problem in validate_gate_payload(payload):
            problems.append(f"validation-report.md: {problem}")


def check_run(run_dir: Path) -> list[str]:
    """Проверить согласованность прогона.

    Args:
        run_dir: Каталог прогона (`output/<run-id>`).

    Returns:
        Список проблем; пустой список означает, что прогон согласован.
    """
    if not run_dir.is_dir():
        return [f"нет каталога прогона: {run_dir}"]

    defined: dict[str, set[str]] = {}
    for family, filename in ARTIFACT_FILES.items():
        defined[family] = _defined(_read(run_dir / filename), family)

    problems: list[str] = []
    fr_text = _read(run_dir / "functional-requirements.md")
    br_text = _read(run_dir / "business-requirements.md")
    trac_text = _read(run_dir / "traceability-matrix.md")
    _check_fr_sources(fr_text, defined["BR"], problems)
    _check_fr_lifecycle(fr_text, problems)
    _check_fr_criteria(fr_text, problems)
    _check_j_persons(_read(run_dir / "jtbd.md"), defined["P"], problems)
    _check_uc_trace(
        _read(run_dir / "use-cases.md"),
        _read(run_dir / "jtbd.md"),
        defined["J"],
        problems,
    )
    _check_diagrams(run_dir / "diagrams", defined, problems)
    _check_br_coverage(fr_text, br_text, trac_text, problems)
    spec_text = _read(run_dir / "spec.md")
    _check_pdn_section(fr_text, spec_text, problems)
    applied = _check_nfr_measurability(
        _read(run_dir / "nonfunctional-requirements.md"), problems
    )
    if not applied:
        spec_nfr = _section(spec_text, "4")
        if spec_nfr is not None:
            _check_nfr_measurability(spec_nfr, problems)
    _check_negative_acceptance(fr_text, problems)
    _check_adr(spec_text, problems)
    _check_traceability(trac_text, defined, problems)
    _check_task_traceability(trac_text, defined["FR"], problems)
    _check_open_questions(_read(run_dir / "open-questions.md"), problems, run_dir)
    _check_gate_reports(_read(run_dir / "validation-report.md"), problems)
    return problems


def main(argv: list[str]) -> int:
    """Точка входа CLI.

    Args:
        argv: Аргументы командной строки (путь к прогону).

    Returns:
        0 — проблем нет; 1 — найдены проблемы; 2 — неверные аргументы.
    """
    if len(argv) < 2:
        print("Использование: check_run.py <output/run-id>")
        return 2
    run_dir = Path(argv[1])
    problems = check_run(run_dir)
    if not problems:
        print(f"check-run: OK ({run_dir})")
        return 0
    print(f"check-run: FAILED ({run_dir}) — {len(problems)} проблем:")
    for problem in problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
