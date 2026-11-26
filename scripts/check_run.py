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
  колонок принимается, как и в lifecycle-проверках.

Запуск: `python3 scripts/check_run.py output/auto-002` или
`make check-run RUN=auto-002`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

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
#: Маркер источника ответа заказчика.
CUSTOMER_ANSWER_MARKER = "ответ заказчика"
#: Регулярка идентификатора вопроса в таблице открытых вопросов.
QUESTION_ID_RE: re.Pattern[str] = re.compile(r"\bQ-\d+\b")


def _question_rows(text: str) -> list[tuple[str, str, str]]:
    """Разобрать строки таблицы открытых вопросов.

    Берутся строки, где первая ячейка — идентификатор вопроса (`Q-*`).
    Формат строки различается между прогонами: в `chat-001` это
    «ID | Вопрос | Ответ (источник) | Статус», в `auto-002` — «ID | Вопрос |
    Почему блокирует | Кто отвечает | Статус». Поэтому берутся первая и
    последняя ячейки, а источник ищется по всему тексту строки.

    Args:
        text: Текст файла `open-questions.md`.

    Returns:
        Список кортежей (идентификатор, текст строки, статус).
    """
    rows: list[tuple[str, str, str]] = []
    for cells in _rows(text):
        if not cells:
            continue
        match = QUESTION_ID_RE.search(cells[0])
        if match is None:
            continue
        status = cells[-1].strip().lower()
        rows.append((match.group(0), " | ".join(cells), status))
    return rows


def _check_open_questions(text: str, problems: list[str]) -> None:
    """Проверить связку «вопрос → ответ» в открытых вопросах.

    Проверяется:
    - идентификаторы вопросов уникальны;
    - закрытый вопрос содержит источник ответа (иначе непонятно, на чём
      основан ответ);
    - открытый вопрос не содержит источника (ответ есть — вопрос не открыт).

    Проверка условна: файл без таблицы вопросов (старый формат прогона)
    пропускается — прогон не ломается из-за отсутствия артефакта, который
    в нём никогда не заполнялся.

    Args:
        text: Текст файла `open-questions.md`.
        problems: Список накопленных проблем (дополняется на месте).
    """
    if not text.strip():
        return

    rows = _question_rows(text)
    if not rows:
        return

    seen: set[str] = set()
    for question_id, row_text, status in rows:
        if question_id in seen:
            problems.append(f"{question_id}: вопрос повторяется в open-questions.md")
        seen.add(question_id)

        has_source = CUSTOMER_ANSWER_MARKER in row_text.lower()
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
    _check_open_questions(_read(run_dir / "open-questions.md"), problems)
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
