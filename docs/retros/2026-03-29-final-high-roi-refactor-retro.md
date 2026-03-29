# Final High-ROI Refactor Retro

## Situation

После нескольких итераций рефакторинга metrics updater приблизился к точке, где следующая архитектурная работа могла легко стать polishing с убывающей отдачей.

Нужно было понять, какой последний шаг ещё даёт реальную пользу, а где уже стоит остановиться.

## What Happened

В качестве последнего high-value шага update/application flow был подтянут ближе к typed domain boundary:

- `upsert_task()` стал работать через `GoalRecord`
- mutation update-path теперь идёт по typed object
- сериализация обратно в persistence-shaped dict осталась на boundary

Это уменьшило зависимость application logic от сырых dict без переписывания CLI, JSON schema или storage contract.

## Root Cause

Главный оставшийся архитектурный разрыв был между уже типизированным domain/summary слоем и update-flow, который всё ещё жил в persistence-shaped dict.

Если бы мы оставили этот разрыв, следующая доменная правка снова тянула бы за собой смешение:

- application orchestration
- domain mutation
- persistence representation

## Retrospective

Этот шаг оказался ценным именно потому, что был последним крупным разрывом с хорошим ROI.

Он дал архитектурную пользу без:

- rewrite
- слома backward compatibility
- миграции схемы
- новой волны продуктового риска

Главный урок здесь не только технический, но и управленческий: важно уметь остановить рефакторинг в точке, где core-risk уже снят, а дальнейшая работа начинает давать всё меньше пользы.

## Conclusions

- Typed boundary в update-flow был оправдан и полезен.
- После этого шага код заметно ровнее как система, а не как набор удачных patches.
- Дальнейший большой рефакторинг уже не выглядит обязательным.

## Permanent Changes

- Update/application path теперь использует `GoalRecord` внутри mutation flow.
- Persistence serialization оставлена на boundary.
- Следующие изменения стоит делать только под новый продуктовый сигнал, баг-класс или доменную потребность, а не ради архитектурного polishing самого по себе.
