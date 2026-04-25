# Runbook

Документ дополняется по ходу реализации. Появится содержательно на этапе 8.

## Базовые команды для дебага

```bash
# Запуск с FakeLLM (без API)
make dry-run

# Запуск с детальным логом
OBSERVABILITY_LOG_LEVEL=DEBUG make demo

# Очистить чекпоинты
rm -rf .checkpoints/
```
