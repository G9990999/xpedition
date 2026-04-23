# Xpedition DS — KOZ-2 Solution

## Описание

Решение задачи автоматического обнаружения объектов историко-культурного наследия по данным дистанционного зондирования Земли (аэрофотосъёмка, лидар).

**Архитектура:** детектор + постобработка → вывод полигонов в формате GeoJSON (EPSG:3857).

Классифицируемые объекты (Приложение 4 Технического регламента):

| Класс | Вес F1 |
|---|---|
| `kurgany_povrezhdennye` | 27.8 % |
| `kurgany_tselye` | 22.2 % |
| `gorodishcha` | 16.7 % |
| `arkhitektury` | 11.1 % |
| `object_poly` | 11.1 % |
| `fortifikatsii` | 5.6 % |
| `finds_points` | 5.5 % |

---

## Окружение

- **ОС:** Ubuntu 22.04 / macOS / Windows 10+
- **Docker-образ:** `python:3.12-slim`
- **Python:** 3.12+

---

## Установка зависимостей

```bash
pip install -r requirements.txt
```

---

## Структура проекта

```
.
├── Dockerfile
├── metadata.json                 # Параметры запуска Docker-образа
├── requirements.txt
├── docs/
│   ├── README.md                 # Этот файл
│   └── ai_declaration.md         # Декларация использования ИИ-инструментов
├── models/                       # Веса обученной модели
├── configs/                      # Конфигурационные файлы
├── scripts/
│   ├── preprocess.py             # Предобработка данных
│   └── train.py                  # Обучение модели
├── inference/
│   └── main.py                   # Единственная точка запуска (entry point)
└── participant_create_submission.py
```

---

## Воспроизведение решения

### 1. Загрузка данных

```bash
python participant_download_s3_data.py --local-dir dataset/
```

### 2. Предобработка

```bash
python scripts/preprocess.py --input dataset/ --output processed_data/
```

### 3. Обучение модели

```bash
python scripts/train.py --config configs/train_config.yaml \
                         --data processed_data/ \
                         --output models/
```

### 4. Инференс (локально)

```bash
python inference/main.py /data/input /data/output/result.geojson
```

### 5. Инференс (Docker)

```bash
docker build -t solution:latest .

docker run --rm \
  -v $(pwd)/dataset/test:/data/input \
  -v $(pwd)/results:/data/output \
  solution:latest
```

### 6. Создание архива для платформы

```bash
python participant_create_submission.py --output submission.zip
```

Затем загрузите `submission.zip` в LeaderBoard платформы.

---

## Формат вывода

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[...]]
      },
      "properties": {
        "class_name": "kurgany_tselye",
        "confidence": 0.85,
        "region_name": "001_НАЗВАНИЕ_РЕГИОНА"
      }
    }
  ]
}
```

Система координат: **EPSG:3857** (Web Mercator).  
Метрика: **Взвешенный экспертный F1** с гибридным мягким сопоставлением.
