# Каталог диаграмм: источник → диаграмма → файл → роль

> Reference для `skills/diagram-generation/SKILL.md`. Загружается только при
> выборе конкретного типа диаграммы, а не вместе с телом скила.

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

## Ограничения

- Новых узлов нет: каждый узел — ID из артефакта или сущность из `spec.md`.
- Одна диаграмма — один источник. Смешение источников ломает трассировку.
- Если источник не заполнен, диаграмма не строится: сначала артефакт, потом
  картинка.
