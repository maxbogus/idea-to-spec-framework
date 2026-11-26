---
name: diagram-generation
description: |
  Диаграммы как производные артефактов: use case, sequence, ER, DFD L0–L3,
  C4 C1–C4, BPMN, activity, gantt и CJM, плюс паки (state, domain-map,
  event-storming, dmn, sipoc, service-blueprint, data-lineage, RAG,
  agent-workflow, prompt-flow, feedback-loop, network-topology, iac, c4-code).
  Узлы берутся из ID требований, а не придумываются: диаграмма, которая не
  выводится из артефакта, не строится.
  Triggers on: диаграмма, use case diagram, sequence, ER, DFD, C4, BPMN,
  activity, gantt, CJM, state, domain map, event storming, DMN, SIPOC,
  data lineage, RAG pipeline, agent workflow, mermaid, mmdc, визуализировать
  требования, паки диаграмм.
allowed-tools: Read Write Bash(mmdc:*)
---

# Skill: генерация диаграмм из требований

## Когда использовать

Когда артефакты требований готовы и нужно «показать» их человеку: человек
лучше читает визуал, чем текст. Применяется на этапах System, Architecture,
Design и Plan.

## Принцип: диаграмма — производная, а не отдельный рисунок

Диаграмма строится **из тех же ID**, что и требования: `J-*` — из `jtbd.md`,
`UC-*` — из `use-cases.md`, данные — из `spec.md §6`, компоненты и
интеграции — из §9, roadmap — из плана PM, персоны — из `personas.md`.
Если диаграмма не выводится из артефакта — она не строится: иначе разойдётся
с требованиями.

## Каталог, паки и форматы

- Каталог «источник → диаграмма → файл → роль» и правила нотаций —
  `references/diagram-catalog.md`.
- **Паки** (`behavior`, `domain`, `process`, `ux`, `data`, `ai`, `infra`,
  `architecture`) — там же: диаграмма, пак, владелец, статус и раздел
  `spec.md`, который её питает. Пак включается только явно
  (`make scaffold RUN=… PACKS=…`) и только если раздел заполнен.
- CJM: этапы, touchpoints, эмоции, боли, лента — `references/cjm.md`.
- Скелеты — `templates/*.mmd` и `templates/*.bpmn`; детерминированный рендер —
  конфиг `templates/mermaid-config.json`.

## Что делать

1. **Возьми источник.** Открой артефакт и выпиши ID/сущности, которые войдут
   в диаграмму. Не придумывай новых.
2. **Выбери тип** по каталогу и загрузи только его reference, а не весь
   каталог: одна нотация за раз.
3. **Сгенерируй Mermaid** в `output/<run-id>/diagrams/*.mmd` по скелету из
   `templates/*.mmd`.
4. **Проверь синтаксис:** каждый узел имеет ID, рёбра ссылаются на
   существующие узлы.
5. **Отрендери PNG** (опционально):
   `mmdc -i diagrams/use-case.mmd -o diagrams/use-case.png -b white`.
   Нужен `@mermaid-js/mermaid-cli` >= 12.0.0 (для `usecase-beta`). Если CLI
   нет — source `.mmd` валиден сам по себе.
6. **Добавь обратную ссылку** на диаграмму в артефакт-источник (в `spec.md`
   или `cjm.md`) для трассируемости.

## Метрики / проверка

- Каждая диаграмма ссылается на источник (ID) и имеет обратную ссылку.
- Нет узлов, которых нет в артефакте.
- Все `*.mmd` синтаксически валидны (рендерятся без ошибок).
- PNG не коммитится по умолчанию; для демо-прогонов допускается.
