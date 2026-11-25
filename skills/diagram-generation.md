# Skill: генерация диаграмм из требований

## Когда использовать

Когда артефакты требований готовы и нужно «показать» их человеку: человек
лучше читает визуал, чем текст. Применяется на этапах System, Architecture,
Design и Plan.

## Принцип: диаграмма — производная, а не отдельный рисунок

Диаграмма строится **из тех же ID**, что и требования:

- JTBD: job stories `J-*` из `jtbd.md` (отвечают на «зачем», источник для UC и CJM);
- Use Case: узлы = `UC-*` из `use-cases.md` (актор = человечек, `usecase-beta`);
- Sequence: шаги того же `UC-*`;
- ER: данные из `spec.md §6`;
- C4 / Component: компоненты и интеграции из `spec.md §9`;
- Activity: ключевой поток из UC;
- Gantt: `roadmap` роли PM;
- CJM: персоны × `UC-*` × user flow.

Если диаграмма не выводится из артефакта — она не строится (иначе
разойдётся с требованиями).

## Каталог

| Источник | Диаграмма | Файл | Роль |
|---|---|---|---|
| `personas.md` + `jtbd.md` + `use-cases.md` + user flow | CJM | `cjm.md` | Designer |
| `use-cases.md` (`UC-*`) × `jtbd.md` (`J-*`) | Use Case (`usecase-beta`) | `diagrams/use-case.mmd` | SA |
| шаги `UC-*` | Sequence | `diagrams/sequence.mmd` | SA |
| `spec.md §6` данные | ER | `diagrams/er.mmd` | SA |
| `personas.md` + `spec.md §6/§9` | DFD L0 (контекст) | `diagrams/dfd-context.mmd` | SA |
| `spec.md §9` процессы и данные | DFD L1 (декомпозиция) | `diagrams/dfd-level1.mmd` | SA |
| `spec.md §9` один процесс из L1 | DFD L2 (под-процессы) | `diagrams/dfd-level2.mmd` | SA |
| `spec.md §9` один под-процесс из L2 | DFD L3 (шаги) | `diagrams/dfd-level3.mmd` | SA |
| `spec.md §9` система и внешние | C4 C1 Context | `diagrams/c4-context.mmd` | Architect |
| `spec.md §9` контейнеры | C4 C2 Container | `diagrams/c4-container.mmd` | Architect |
| `spec.md §9` модули API | C4 C3 Component | `diagrams/c4-component.mmd` | Architect |
| `spec.md §9` + зоны доверия | C4 C4 Deployment | `diagrams/c4-deployment.mmd` | Architect |
| ключевой `UC-*` | BPMN 2.0 (визуал + XML) | `diagrams/bpmn-process.mmd`, `bpmn-process.bpmn` | SA |
| ключевой поток (упрощённо) | Activity | `diagrams/activity.mmd` | Architect |
| `roadmap` | Gantt | `diagrams/gantt.mmd` | PM |

## Форматы

- **Mermaid** (`.mmd`) — всё, что рендерится `mmdc`: use case (`usecase-beta`,
  Mermaid >= 12.0.0; актор — человечек, use case — овал), C4 (`C4Context`,
  `C4Container`, `C4Component`, `C4Deployment`), DFD (`flowchart` с
  `classDef external/process/storage`), BPMN-приближение (`flowchart`).
- **BPMN 2.0 XML** (`.bpmn`) — канонический формат для bpmn.io / Camunda.
  `mmdc` его не рендерит; валидируется как XML (`make check-bpmn`).
- **DFD** — уровни 0 (контекст) и 1–3 (декомпозиция): L1 — система →
  процессы, L2 — процесс → под-процессы, L3 — под-процесс → шаги; нотация
  ГОСТ 2.701 / ISO 5807 (по мотивам `telemetry`).
- **C4** — C1 Context / C2 Container / C3 Component / C4 Deployment (по
  мотивам `architectureKata`).

Детерминированный рендер: `templates/mermaid-config.json`
(`deterministicIds: true`), передаётся в `mmdc` через `-c`.

## Что делать

1. **Возьми источник.** Открой артефакт и выпиши ID/сущности, которые войдут
   в диаграмму. Не придумывай новых.
2. **Сгенерируй Mermaid** в `output/<run-id>/diagrams/*.mmd` по скелету из
   `templates/*.mmd`.
3. **Проверь синтаксис:** каждый узел имеет ID, рёбра ссылаются на
   существующие узлы.
4. **Отрендери PNG** (опционально):
   `mmdc -i diagrams/use-case.mmd -o diagrams/use-case.png -b white`.
   Нужен `@mermaid-js/mermaid-cli` **>= 12.0.0** (для `usecase-beta`). Если CLI нет — source `.mmd` валиден сам
   по себе, PNG генерится позже.
5. **Добавь обратную ссылку** на диаграмму в артефакт-источник (в `spec.md`
   или `cjm.md`) для трассируемости.

## CJM (карта пути клиента)

CJM — таблица этапов с эмоциями и болями плюс визуальная лента:

- этап → touchpoint → действие → эмоция → боль → возможность;
- внизу — mermaid `flowchart LR` с этапами;
- 2–3 строки нарратива от лица персоны (как `user-journey-alexey.md`).

CJM обязана опираться на конкретную персону из `personas.md`, её JTBD из
`jtbd.md` и `UC-*` из `use-cases.md`.

## Метрики / проверка

- Каждая диаграмма ссылается на источник (ID) и имеет обратную ссылку.
- Нет узлов, которых нет в артефакте.
- Все `*.mmd` синтаксически валидны (рендерятся без ошибок).
- PNG не коммитится по умолчанию; для демо-прогонов допускается.
