# Missing Merge Invariant Tests Retro

## Situation

Во время bug review в `merge_tasks()` нашлись реальные дефекты, хотя команда уже была покрыта тестами на успешный merge.

Проблема оказалась не в полном отсутствии тестов, а в том, что тестовый слой проверял в основном happy path и не проверял инварианты опасных состояний.

## What Happened

Старые тесты подтверждали, что:

- merge объединяет attempts
- merge сохраняет timestamps
- merge корректно ведёт себя при неполном cost
- merge отклоняет `in_progress`

Но они не проверяли:

- merge goals разных `goal_type`
- merge, который создаёт supersession cycle
- прозрачность reconstructed inferred entries в human-readable report

В итоге команда была “покрыта”, но покрытие не защищало от самых рискованных semantic failures.

## Root Cause

Мы тестировали сценарии использования, но недостаточно тестировали invariants.

То есть мышление при проектировании тестов было таким:

- “докажи, что команда работает”

а нужно было ещё добавлять второй слой:

- “докажи, что команда не может создать невалидное состояние”

Для mutating admin-like commands второй слой особенно важен, потому что их основные риски часто лежат не в happy path, а в разрушении модели данных.

## Retrospective

Это хороший урок про качество тестов:

- наличие happy-path tests ещё не означает хорошее bug resistance
- coverage по количеству сценариев не равно coverage по invariants
- команды, меняющие историю, связи и классификацию данных, требуют adversarial tests по умолчанию

Главный пропуск был не технический, а мыслительный: мы не оформили для себя явное правило, что каждая mutating command должна иметь tests трёх типов:

1. happy path
2. invalid-state rejection
3. report/summary consistency after mutation

## Conclusions

- Баг не находился раньше, потому что тесты были слишком ориентированы на “успешно отработал основной кейс”.
- Для merge-подобных команд нужно проектировать tests от инвариантов, а не только от сценариев использования.
- Review всё ещё полезен, но такие дефекты должны ловиться automated tests раньше code review.

## Permanent Changes

- Для каждой mutating command в metrics updater заранее писать tests в трёх корзинах:
  - happy path
  - invariant rejection
  - summary/report consistency
- Для команд, меняющих связи между goals или entries, обязательно добавлять tests на cycle, type drift и history corruption.
- Считать “команда покрыта тестами” правдой только если покрыты не только успешные сценарии, но и запрещённые состояния.
