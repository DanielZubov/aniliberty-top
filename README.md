# Aniliberty Torznab

[![Build and Push Docker Image](https://github.com/DanielZubov/aniliberty-top/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/DanielZubov/aniliberty-top/actions/workflows/docker-publish.yml)
[![ghcr.io](https://img.shields.io/badge/ghcr.io-aniliberty--top-blue?logo=docker)](https://github.com/DanielZubov/aniliberty-top/pkgs/container/aniliberty-top)
[![Latest Release](https://img.shields.io/github/v/release/DanielZubov/aniliberty-top?sort=semver)](https://github.com/DanielZubov/aniliberty-top/releases/latest)

Torznab-индексатор для [Aniliberty](https://www.aniliberty.top/) — позволяет искать аниме-релизы прямо из [Prowlarr]([https://prowlarr.com/](https://github.com/prowlarr/prowlarr)) и других *arr-приложений.

---

## ✨ Возможности

- 🔍 Поиск релизов с Aniliberty через Torznab API
- 🎬 Поддержка поиска по названию, сезону и эпизоду
- 🔌 Прямая интеграция с Prowlarr / Sonarr / Radarr
- 🐳 Готовый Docker-образ (multi-arch, публичный)
- ⚡ Лёгкий и быстрый — только Python и минимум зависимостей

---

## 🚀 Быстрый старт

### Docker Compose (рекомендуется)

```yaml
services:
  anilibria-torznab:
    image: ghcr.io/danielzubov/aniliberty-top:latest
    container_name: anilibria-torznab
    restart: unless-stopped
    ports:
      - "8020:8020"
    environment:
      - TZ=Europe/Moscow
      - PYTHONUNBUFFERED=1
```

```bash
docker compose up -d
```

### Docker CLI

```bash
docker run -d \
  --name anilibria-torznab \
  --restart unless-stopped \
  -p 8020:8020 \
  -e TZ=Europe/Moscow \
  ghcr.io/danielzubov/aniliberty-top:latest
```

Индексатор будет доступен по адресу: `http://<your-host>:8020`

---

## ⚙️ Настройка в Prowlarr

1. Откройте Prowlarr → **Settings** → **Indexers** → **Add Indexer**.
2. Выберите **Generic Torznab**.
3. Заполните поля:
   - **Name**: `Aniliberty`
   - **URL**: `http://<ip-вашего-сервера>:8020`
   - **API Path**: `/api`
   - **API Key**: *оставьте пустым или укажите значение, если задано в конфиге*
4. Нажмите **Test**, затем **Save**.

Готово — теперь релизы Aniliberty доступны во всех подключённых *arr-приложениях.

---

## 🔧 Переменные окружения

| Переменная         | По умолчанию | Описание                          |
|--------------------|--------------|-----------------------------------|
| `TZ`               | `UTC`        | Часовой пояс контейнера           |
| `PYTHONUNBUFFERED` | `1`          | Небуферизованный вывод (для логов)|

---

## 📦 Образы

Образы публикуются автоматически при каждом пуше в `main` и при создании тега:

| Тег               | Описание                          |
|-------------------|-----------------------------------|
| `latest`          | Последняя сборка из ветки `main`  |
| `v1.0.0`, `v1.1`  | Конкретные версии (по git-тегам)  |

```bash
docker pull ghcr.io/danielzubov/aniliberty-top:latest
```

---

## 🛠 Сборка из исходников

```bash
git clone https://github.com/DanielZubov/aniliberty-top.git
cd aniliberty-top
docker compose up -d --build
```

---

## 📄 Лицензия

MIT
