# ADR 0003 — Image Redaction выполняется ДО Vision

**Status**: Accepted
**Date**: 2026-04-25

## Context

ТЗ §23 предписывает порядок: `collect → redact → describe`. Альтернатива — Vision сначала, затем redaction текста — даёт лучшее качество классификации, но Vision видит сырое изображение с PII.

## Decision

`Presidio Image Redactor` закрашивает PII прямо на изображении (чёрные прямоугольники по bbox'ам PII) ДО передачи в Vision.

## Альтернативы

| Вариант | Почему не выбран |
|---|---|
| Vision → Redaction (текст) | Vision видит сырое изображение с PII — privacy leak в LLM-логи и трассировку |
| Гибрид: 2 прохода Vision | Дорого в 2 раза по токенам, нет преимуществ перед однопроходным с image redaction |

## Consequences

- ➕ PII не уходят во внешний LLM в любом случае (соответствие ТЗ §23, GDPR)
- ➕ Простой одношаговый пайплайн
- ➖ Image redaction может закрасить контекст, важный для классификации (например, всё письмо целиком)
- ➖ Mitigation: Vision-промпт обучен интерпретировать чёрные маски как "PII скрыт" и классифицировать по visible UI elements
- ➖ Дополнительная зависимость: Presidio + Tesseract OCR (внутри Image Redactor)

## Защитный слой

После Vision дополнительно прогоняем `RegexRedactor.redact_text()` на `visible_text` — на случай если Presidio пропустил что-то на изображении.
