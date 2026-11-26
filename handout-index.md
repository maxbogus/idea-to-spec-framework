# Handout Index — синхронизация промптов, скилов и методов

> Единый источник правды: какая роль какой метод и скил применяет, какой
> артефакт создаёт и на каком гейте проверяется. Если роль, метод, скил и
> артефакт расходятся — правим здесь, а не в пяти файлах по отдельности.

## Три слоя знаний

| Слой | Папка | Что это | Пример |
|---|---|---|---|
| Промпты | `prompts/` | роли и правила | `prompts/roles/system-analyst.md` |
| Навыки (методы) | `methods/` | методики, общие для ролей | `fact-hypothesis-forecast.md` |
| Скилы | `skills/` | повторяемые процедуры | `detect-contradictions.md` |

## Сквозная таблица

| Роль | Промпт | Методы (навыки) | Скилы | Артефакты | Гейт |
|---|---|---|---|---|---|
| Оркестратор | `prompts/orchestrator.md` | все (диспетчер) | все (диспетчер) | `brief.md`, `open-questions.md`, `run-report.md` (итоговый отчёт, в т.ч. «Метрики прогона») | — |
| Product Manager | `prompts/roles/product-manager.md` | `variants.md`, `strategy-and-verification.md`, `decision-keeper.md` | `collect-sources.md`, `analyze-data.md` | `business-requirements.md` (ценность, варианты, OST, приоритизация, PMF, GTM) | BA-gate |
| Business Analyst | `prompts/roles/business-analyst.md` | `fact-hypothesis-forecast.md` | `mock-respondents.md`, `collect-sources.md` | `personas.md`, `jtbd.md`, `business-requirements.md` (scope по MoSCoW, конкурентный анализ, privacy impact) | BA-gate |
| System Analyst | `prompts/roles/system-analyst.md` | `fact-hypothesis-forecast.md` | `detect-contradictions.md`, `analyze-data.md`, `quantify-nfr.md`, `define-acceptance.md`, `diagram-generation.md` | `use-cases.md`, `functional-requirements.md` (BDD-AC, compliance, threat model), `nonfunctional-requirements.md`, `spec.md`, `diagrams/use-case.mmd`, `sequence.mmd`, `er.mmd`, `dfd-context.mmd`, `dfd-level1.mmd`, `dfd-level2.mmd`, `dfd-level3.mmd` | SA-gate |
| Architect | `prompts/roles/architect.md` | `decision-keeper.md` | `detect-contradictions.md`, `record-decision.md`, `diagram-generation.md` | ADR (с альтернативами) и интеграции в `spec.md`, `diagrams/c4-context.mmd`, `c4-container.mmd`, `activity.mmd` | Spec-gate |
| Designer | `prompts/roles/designer.md` | — | `mock-respondents.md`, `diagram-generation.md` | `cjm.md`, user flow / wireframe в `spec.md`, accessibility (WCAG), heuristic evaluation, design tokens | — |
| Project Manager | `prompts/roles/project-manager.md` | `decision-keeper.md`, `strategy-and-verification.md` | `analyze-data.md`, `diagram-generation.md` | `traceability-matrix.md` (задача `T-*` → `FR-*`/`BR-*` → статус покрытия), `risk-register.md`, `human-oversight-plan.md`, WBS / critical path / buffer, `diagrams/gantt.mmd` | Spec-gate |
| Fact-check (субагент) | `subagents/fact-check.md` | `fact-hypothesis-forecast.md` | — | `validation-report.md`, `hallucination-log.md` | Spec-gate |
| Критик (субагент) | `subagents/requirements-critic.md` | — | `detect-contradictions.md` | раздел «Качество и полнота» в `validation-report.md`, `open-questions.md` | Spec-gate |
| Гейт (роль) | `prompts/roles/gate-reviewer.md` | — | — | `checks[]` по чеклисту в `validation-report.md` §«Гейты» | BA-gate / SA-gate / Spec-gate |

## Региональные чек-листы

Справочные материалы (`templates/regional/`) — не артефакты прогона, в
`output/` не копируются. Роль читает чек-лист по контуру.

| Контур | Чек-лист | Кто применяет |
|---|---|---|
| ЕС, обработка ПДн | `templates/regional/gdpr-checklist.md` | BA, SA, Architect |
| Россия, ПДн граждан РФ | `templates/regional/152-fz-checklist.md` | BA, SA, Architect |
| Китай, ПДн граждан КНР | `templates/regional/pipl-checklist.md` | BA, SA, Architect |
| США, медицина / платежи | `templates/regional/hipaa-checklist.md` | BA, SA, Architect |

Источник правды по стандартам — `standards-mapping.md`.

## Диаграммы

Диаграмма — производная от артефакта, а не отдельный рисунок
(`skills/diagram-generation/SKILL.md`). Каталог «источник → диаграмма»:

| Источник | Диаграмма | Файл |
|---|---|---|
| `personas.md` + `jtbd.md` + `use-cases.md` + user flow | CJM | `cjm.md` |
| `use-cases.md` (`UC-*`) × `jtbd.md` (`J-*`) | Use Case (`usecase-beta`) | `diagrams/use-case.mmd` |
| шаги `UC-*` | Sequence | `diagrams/sequence.mmd` |
| `spec.md §6` данные | ER | `diagrams/er.mmd` |
| `personas.md` + `spec.md §6/§9` | DFD L0 (контекст) | `diagrams/dfd-context.mmd` |
| `spec.md §9` процессы и данные | DFD L1 (декомпозиция) | `diagrams/dfd-level1.mmd` |
| `spec.md §9` один процесс из L1 | DFD L2 (под-процессы) | `diagrams/dfd-level2.mmd` |
| `spec.md §9` один под-процесс из L2 | DFD L3 (шаги) | `diagrams/dfd-level3.mmd` |
| `spec.md §9` система и внешние | C4 C1 Context | `diagrams/c4-context.mmd` |
| `spec.md §9` контейнеры | C4 C2 Container | `diagrams/c4-container.mmd` |
| `spec.md §9` модули API | C4 C3 Component | `diagrams/c4-component.mmd` |
| `spec.md §9` + зоны доверия | C4 C4 Deployment | `diagrams/c4-deployment.mmd` |
| ключевой `UC-*` | BPMN 2.0 | `diagrams/bpmn-process.mmd`, `bpmn-process.bpmn` |
| ключевой поток (упрощённо) | Activity | `diagrams/activity.mmd` |
| `roadmap` | Gantt | `diagrams/gantt.mmd` |

**Паки диаграмм** (только по явному `PACKS=...`, см. `prompts/start.md`):

| Пак | Диаграммы | Источник | Владелец |
|---|---|---|---|
| `behavior` | `state.mmd` | `spec.md §18` | SA |
| `domain` | `domain-map.mmd`, `event-storming.mmd` | `spec.md §11` | SA |
| `process` | `dmn.mmd`, `sipoc.mmd` | `spec.md §15`, `§16` | BA/SA |
| `ux` | `service-blueprint.mmd` | `spec.md §17` + `cjm.md` | Designer |
| `data` | `data-lineage.mmd` | `spec.md §12` | SA |
| `ai` | `rag-pipeline.mmd`, `vector-schema.mmd`, `agent-workflow.mmd`, `prompt-flow.mmd`, `feedback-loop.mmd` | `spec.md §13` | SA/Architect |
| `infra` | `network-topology.mmd`, `iac.mmd` | `spec.md §14` | Architect |
| `architecture` | `c4-code.mmd` | `spec.md §9` | Architect |

Условные разделы §11–§18 в `templates/spec-template.md`: раздел не заполнен —
диаграмма не строится. Reference-only артефакты (Wardley, ArchiMate, SysML,
DMN XML) — `docs/visual-artifacts.md`, не генерируются.

Форматы: `.mmd` — Mermaid (use case — нативный `usecase-beta`, C4, DFD, BPMN-приближение,
activity, gantt), рендерится `mmdc` (>= 12.0.0); `.bpmn` — канонический BPMN 2.0 XML для bpmn.io/Camunda,
валидируется как XML (`make check-bpmn`). Рендер (опционально):
`mmdc -i x.mmd -o x.png -b white -c templates/mermaid-config.json`.
PNG не коммитится по умолчанию — только source `.mmd`.

## Проверка синхронизации

Механическая проверка: `make check-sync`.

- [ ] каждая роль из `prompts/roles/` есть в таблице;
- [ ] каждый метод из `methods/` используется хотя бы одной ролью;
- [ ] каждый скил из `skills/` используется хотя бы одной ролью;
- [ ] каждый артефакт из `templates/` имеет владельца-роль;
- [ ] каждая диаграмма из `templates/*.mmd` выводится из артефакта-источника;
- [ ] у каждого гейта есть владелец и чеклист в `prompts/gate-checklists.md`;
- [ ] стартовый промпт `prompts/start.md` ссылается только на существующие
      файлы.

## Терминология

- **Факт / гипотеза / прогноз** — единая триада из
  `methods/fact-hypothesis-forecast.md`. «Допущение» — частный случай
  гипотезы, а не отдельное состояние.
- **Скил** — «как сделать»; **метод (навык)** — «по какому правилу решать»;
  **промпт** — «кто делает и в каком формате отвечает».
- **JTBD** — работа, которую персона «нанимает» продукт выполнить
  (`templates/jtbd.md`); **CJM** — карта пути с эмоциями и болями
  (`templates/cjm.md`).
