- [x] не считаю прошлую задачу успешной, ибо не фига не появилось то, что нужно
- [x] переход на goal
[x] 
```commandline
Read AGENTS.md and docs/codex-metrics-policy.md first.

Audit our metrics system for:
- Success Rate
- Attempts per Closed Task
- Failure Reasons

Verify that the script, tests, JSON output, and markdown report all match the intended definitions.
Run tests and smoke checks.
Fix inconsistencies if found.
Then summarize the result.
```
 - [x] еще раз собираем продуктовое вижен
 - [x] мелкие правки юзабельности
 - [x] пройди еще раз по графикам цены, почему-то при подсчете последнем, цена всегда null
 - [x] общую ретру и обновление локального агентс
 - [x] сделай кодревью
- [x] сделать какой-то билд готовый, который можно выкладывать будет на гитхабл, в публичный достуи и интеграцию в другую проекты
- добавить автоматическую публикацию release artifacts в GitHub Releases
- подготовить отдельный publish path для PyPI
- отдельно исследовать и решить, нужен ли standalone binary не-Python формата
- далее общаться к пм и там идеи поискать
- [x] переделать документацию по продуктовым гипотезам, чтобы с ней было удобно работать
- добавить ретро-флоу с аудитом качества метрик по задаче
- продумать авто-снимок task metrics в тексте ретры (status, attempts, failure_reason, cost/tokens)
- [x] зачисть md файлы, минимазция policy
- [x] видимо надо чтобы ид генерировлся скриптом
 - попробовать перейти на схему разработка через таски с обычными флоу (требования, анализ, разработка, кодревью, qa, демо клиенту, ретроспектива), общение только через лида, а разработка только через таски
