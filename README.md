# Autoshina Postavshiki — Агрегатор поставщиков шин и дисков

Сервис объединяет ассортимент 4 поставщиков шин и дисков в единую XML-выгрузку. Поддерживается:

- Периодическая загрузка XML по расписанию (HTTP/HTTPS)
- Адаптеры для нормализации формата каждого поставщика
- Дедупликация по характеристикам и названию
- Выбор cheapest available при дублях
- REST API: GET /export/tires.xml, GET /export/wheels.xml
- Флаг активности поставщика (active: false — не обрабатываем)
- Обработка сетевых ошибок, retry, изоляция сбоев
- Кэш: XML сначала скачивается в `data/cache/`, затем парсится (подходит для больших выгрузок)

## Установка

```bash
pip install -r requirements.txt
```

При ошибке pip в старом venv (AttributeError: ImpImporter) пересоздайте окружение:

```bash
python -m venv venv --clear
.\venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Запуск

```bash
python main.py
```

API будет доступен на http://localhost:8000

- `GET /export/tires.xml` — выгрузка шин
- `GET /export/wheels.xml` — выгрузка дисков
- `GET /health` — проверка работы

## Конфигурация

- `config/suppliers.yaml` — список поставщиков, URL, флаг active, интервал обновления, cache_dir
- `config/adapters/supplier_N.yaml` — маппинг полей и правил для каждого поставщика

## Структура проекта

```
├── config/
│   ├── suppliers.yaml
│   └── adapters/
├── src/
│   ├── loader.py      # Загрузка XML
│   ├── adapters/      # Адаптеры
│   ├── storage.py     # SQLite
│   ├── deduplicator.py
│   ├── export.py
│   ├── sync.py
│   └── scheduler.py
├── api/
│   └── app.py
├── data/
│   ├── cache/          # Кэш загруженных XML (supplier_1_tires.xml и т.д.)
│   └── products.db     # SQLite БД
└── main.py
```
