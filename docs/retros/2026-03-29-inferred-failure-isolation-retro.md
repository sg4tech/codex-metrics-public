# Inferred Failure Isolation Retro

## Situation

После перехода на настоящий attempt-history log система стала честнее отражать retry pressure, но появился побочный эффект: synthetic inferred attempts начали попадать в `failure_reasons` и размывать диагностическую ценность метрики.

## What Happened

Когда goal имел больше attempts, чем явно наблюдаемых attempt entries, updater восстанавливал недостающую историю и создавал failed entries с `failure_reason="other"`.

Операционно это помогало сохранить форму истории, но аналитически создавало ложный сигнал: breakdown причин фейлов описывал не только реальные проблемы, но и технически восстановленные записи.

## Root Cause

Система смешивала две разные цели в одном поле:

- operational history completeness
- diagnostic failure attribution

`failure_reason` использовался и как средство заполнить inferred history, и как реальная аналитическая метка.

## Retrospective

Это хороший пример того, что метрика может стать формально полной, но хуже как инструмент принятия решений.

Для истории важно сохранить, что лишняя попытка была.
Для диагностики важно не приписывать ей искусственную причину, которой в наблюдаемых данных не было.

## Conclusions

- Inferred attempts полезны как operational log.
- Inferred attempts вредны как источник diagnostic failure reasons.
- History completeness и diagnostic attribution должны быть разведены явно.

## Permanent Changes

- Attempt entries получили явный `inferred` marker.
- Inferred failed entries больше не учитываются в `failure_reasons`.
- Policy и AGENTS закрепляют, что reconstructed history не должна загрязнять диагностические метрики.
