# Xpedition DS — KOZ-2

## Описание

Решение задачи автоматического обнаружения объектов историко-культурного наследия по данным дистанционного зондирования Земли в рамках конкурса **KOZ-2 (Xpedition DS)**.

Поддерживаемые форматы входных данных: аэрофотоснимки (GeoTIFF), данные лидара (LAS/LAZ), векторные аннотации (GeoJSON).

## Требования

- Python 3.12+
- Docker (для запуска в контейнере)

```bash
pip install -r requirements.txt
```

## Быстрый старт

```bash
# Инференс (локально)
python inference/main.py /data/input /data/output/result.geojson

# Инференс (Docker)
docker build -t solution:latest .
docker run --rm \
  -v $(pwd)/dataset/test:/data/input \
  -v $(pwd)/results:/data/output \
  solution:latest

# Создание архива для платформы
python participant_create_submission.py --output submission.zip
```

## Структура проекта

```
.
├── Dockerfile
├── metadata.json
├── requirements.txt
├── docs/
│   ├── README.md             # Детальная документация
│   └── ai_declaration.md     # Декларация использования ИИ-инструментов
├── models/                   # Веса модели
├── configs/
│   └── train_config.yaml
├── scripts/
│   ├── preprocess.py
│   └── train.py
├── inference/
│   └── main.py               # Точка входа (entry point)
└── participant_create_submission.py
```

Подробнее: [docs/README.md](docs/README.md)
