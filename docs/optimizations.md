# Оптимизации обработки эмбеддингов и векторного поиска

## Обзор

Документ описывает реализованные оптимизации для улучшения производительности обработки эмбеддингов и векторного поиска в FinDocBot.

## Реализованные оптимизации

### 1. Переиспользование HTTP-клиента в OllamaGateway

**Проблема:** Каждый запрос к Ollama API создавал новый `httpx.AsyncClient`, что приводило к overhead на установку соединений.

**Решение:** Добавлены lifecycle методы `start()` и `stop()` для управления единым HTTP-клиентом на протяжении всего жизненного цикла приложения.

**Файл:** `src/findocbot/infrastructure/ollama_gateway.py`

**Изменения:**
- Добавлено поле `_client: httpx.AsyncClient | None`
- Метод `start()` инициализирует клиент
- Метод `stop()` корректно закрывает соединения
- Методы `embed_one()`, `embed_many()`, `generate()` используют переиспользуемый клиент

**Преимущества:**
- Снижение latency за счет переиспользования TCP-соединений
- Уменьшение overhead на создание/уничтожение клиентов
- Более эффективное использование connection pooling

### 2. LRU-кеширование эмбеддингов запросов с TTL и метриками

**Проблема:** Повторяющиеся пользовательские запросы вычисляли эмбеддинги заново, что неэффективно. Отсутствовали метрики для мониторинга эффективности кеша в production.

**Решение:** Создан `CachedEmbeddingGateway` — wrapper с LRU-кешем, TTL и метриками для эмбеддингов пользовательских запросов.

**Файл:** `src/findocbot/infrastructure/cached_embedding_gateway.py`

**Архитектура:**
- Использует `OrderedDict` для реализации LRU-логики
- Кеширует только `embed_one()` (пользовательские запросы)
- НЕ кеширует `embed_many()` (чанки документов — уникальны)
- Ключ кеша: SHA256 хеш текста запроса
- Хранит timestamp для каждой записи для поддержки TTL

**Новые возможности:**

1. **Метрики кеша:**
   - Счетчики hits/misses для отслеживания эффективности
   - Метод `get_stats()` возвращает `CacheStats` с метриками
   - Автоматическое логирование статистики при shutdown
   - Hit rate для оценки эффективности кеширования

2. **TTL (Time To Live):**
   - Опциональный параметр `ttl_seconds` для автоматического истечения записей
   - Проверка TTL при каждом доступе к кешу
   - Автоматическое удаление устаревших записей
   - По умолчанию: 3600 секунд (1 час)

3. **Warning при большом размере:**
   - Автоматическое предупреждение при `cache_size > 10000`
   - Помогает избежать чрезмерного потребления памяти

**Конфигурация:**
- Параметр `embedding_cache_size` в `Settings` (по умолчанию: 1000)
- Параметр `embedding_cache_ttl_seconds` в `Settings` (по умолчанию: 3600)
- Настраивается через переменные окружения или код

**Преимущества:**
- Мгновенный ответ для повторяющихся запросов
- Снижение нагрузки на Ollama API
- Экономия вычислительных ресурсов
- Production-ready метрики для мониторинга
- Автоматическая очистка устаревших данных

**Пример использования:**
```python
# В container.py
ollama_gateway = OllamaGateway(...)
provider = CachedEmbeddingGateway(
    gateway=ollama_gateway,
    cache_size=settings.embedding_cache_size,
    ttl_seconds=settings.embedding_cache_ttl_seconds,
)

# Получение метрик
stats = provider.get_stats()
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Cache size: {stats.size}/{stats.max_size}")
```

### 3. Автоматический батчинг эмбеддингов в Gateway

**Проблема:** Большие документы с сотнями чанков отправляли все эмбеддинги одним запросом, что могло вызвать timeout или перегрузку API. Батчинг в use case нарушал принципы чистой архитектуры — use case не должен знать о деталях реализации.

**Решение:** Батчинг перенесен из `UploadPDFUseCase` в `OllamaGateway`, где он является деталью реализации, невидимой для use cases.

**Файл:** `src/findocbot/infrastructure/ollama_gateway.py`

**Изменения:**
- Добавлен параметр `batch_size` в конструктор `OllamaGateway` (по умолчанию: 50)
- Метод `embed_many()` автоматически разбивает большие списки на батчи
- Результаты батчей прозрачно объединяются в единый список
- Use cases просто вызывают `embed_many()` без знания о батчинге

**Конфигурация:**
- Параметр `embedding_batch_size` в `Settings` (по умолчанию: 50)
- Передается в `OllamaGateway` через `container.py`

**Преимущества:**
- Предотвращение timeout на больших документах
- Более стабильная работа с API
- Возможность обработки документов любого размера
- **Соблюдение принципов чистой архитектуры** — use case не знает о деталях реализации
- Прозрачность для всех use cases

**Пример кода:**
```python
# В OllamaGateway.embed_many()
async def embed_many(self, texts: list[str]) -> list[list[float]]:
    """Embed many chunk texts with automatic batching."""
    if not texts:
        return []
    
    # Process in batches to avoid timeout on large documents
    all_embeddings: list[list[float]] = []
    client = self._get_client()
    
    for i in range(0, len(texts), self._batch_size):
        batch = texts[i : i + self._batch_size]
        response = await client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._embed_model, "input": batch},
        )
        response.raise_for_status()
        payload = response.json()
        all_embeddings.extend(payload["embeddings"])
    
    return all_embeddings

# Use case теперь просто:
embeddings = await self._provider.embed_many([c.text for c in built_chunks])
```

### 4. Lifecycle управление в AppContainer

**Проблема:** Отсутствовало централизованное управление жизненным циклом компонентов с внешними ресурсами.

**Решение:** Обновлен `AppContainer` для управления lifecycle provider'а.

**Файл:** `src/findocbot/infrastructure/container.py`

**Изменения:**
- Добавлено поле `provider: CachedEmbeddingGateway` в контейнер
- Метод `startup()` вызывает `provider.start()`
- Метод `shutdown()` вызывает `provider.stop()` для корректной очистки

**Преимущества:**
- Гарантированная инициализация ресурсов при старте
- Корректное освобождение ресурсов при остановке
- Централизованное управление lifecycle

## Конфигурация

Новые параметры в `src/findocbot/config.py`:

```python
@dataclass(frozen=True)
class Settings:
    # ... существующие параметры ...
    embedding_cache_size: int = 1000                    # Размер LRU-кеша для эмбеддингов
    embedding_batch_size: int = 50                      # Размер батча при загрузке документов
    embedding_cache_ttl_seconds: int | None = 3600      # TTL для записей кеша (1 час)
```

Переопределение через переменные окружения:
```bash
export EMBEDDING_CACHE_SIZE=2000
export EMBEDDING_BATCH_SIZE=100
export EMBEDDING_CACHE_TTL_SECONDS=7200  # 2 часа
```

## Тестирование

Созданы comprehensive тесты в `tests/test_embedding_cache.py`:

1. **test_cached_gateway_caches_identical_queries** — проверка кеширования идентичных запросов
2. **test_cached_gateway_does_not_cache_embed_many** — проверка отсутствия кеша для batch операций
3. **test_cached_gateway_respects_cache_size** — проверка соблюдения размера кеша и LRU-логики
4. **test_cached_gateway_clears_cache_on_stop** — проверка очистки кеша при остановке
5. **test_cached_gateway_tracks_metrics** — проверка корректности метрик hits/misses и hit rate
6. **test_cached_gateway_respects_ttl** — проверка истечения записей по TTL
7. **test_cached_gateway_without_ttl** — проверка работы без TTL (бесконечное хранение)
8. **test_ollama_gateway_batching** — проверка батчинга в OllamaGateway

Все тесты проходят успешно.

## Метрики производительности

### Ожидаемые улучшения:

1. **Повторяющиеся запросы:**
   - Без кеша: ~200-500ms (вызов Ollama API)
   - С кешем: <1ms (чтение из памяти)
   - **Ускорение: 200-500x**

2. **Загрузка больших документов:**
   - Без батчинга: риск timeout на >100 чанков
   - С батчингом: стабильная обработка любого размера
   - **Надежность: значительно повышена**

3. **HTTP-соединения:**
   - Без переиспользования: новое соединение на каждый запрос
   - С переиспользованием: единое соединение
   - **Снижение latency: 10-50ms на запрос**

## Мониторинг

Кеш предоставляет встроенные метрики для production мониторинга:

```python
# Получение метрик кеша
stats = provider.get_stats()

print(f"Cache hits: {stats.hits}")
print(f"Cache misses: {stats.misses}")
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Current size: {stats.size}/{stats.max_size}")

# Метрики автоматически логируются при shutdown:
# INFO: Cache stats: 150 hits, 50 misses, hit rate: 75.00%, final size: 45
```

**Интеграция с Prometheus (будущее улучшение):**
```python
from prometheus_client import Counter, Gauge

cache_hits = Counter('embedding_cache_hits_total', 'Total cache hits')
cache_misses = Counter('embedding_cache_misses_total', 'Total cache misses')
cache_size = Gauge('embedding_cache_size', 'Current cache size')
```

## Дальнейшие оптимизации

Возможные направления для будущих улучшений:

1. **Кеширование результатов векторного поиска** — кешировать не только эмбеддинги, но и результаты поиска
2. **Предварительный прогрев кеша** — загрузка популярных запросов при старте
3. **Персистентный кеш** — сохранение кеша на диск для переиспользования между перезапусками
4. **Prometheus метрики** — интеграция с Prometheus для централизованного мониторинга
5. **Адаптивный batch size** — динамическая настройка размера батча в зависимости от нагрузки
6. **Распределенный кеш** — использование Redis для shared кеша между инстансами

## Совместимость

Все оптимизации:
- ✅ Обратно совместимы с существующим API
- ✅ Не требуют изменений в клиентском коде
- ✅ Прозрачны для use cases
- ✅ Следуют архитектуре Ports and Adapters
- ✅ Покрыты тестами

## Заключение

Реализованные оптимизации значительно улучшают производительность системы при работе с эмбеддингами и векторным поиском, сохраняя при этом чистоту архитектуры и обратную совместимость.
