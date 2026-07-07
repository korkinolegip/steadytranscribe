# SteadyTranscribe — конфиг агента

## Обзор
Windows-приложение (Windows 10/11) локальной транскрипции аудио/видео для пиар-отдела SteadyControl: закинул запись Zoom → получил текст, при желании разделил по собеседникам. Всё офлайн (записи конфиденциальны). Воспроизводит функцию File Transcription из FluidVoice + оболочку + брендинг SteadyControl. Издатель: Oleg Korkin (SteadyControl automation). Репо: github.com/korkinolegip/steadytranscribe (публичный).

## Стек
Python 3.12 · PySide6 (Qt, тёмная тема #3AC8C6) · faster-whisper (CTranslate2, int8) · ffmpeg (вшит) · sherpa-onnx диаризация (модели вшиты) · SQLite · PyInstaller + Inno Setup · GitHub Actions (windows-latest)

## Правила
- Работаем по `METHODOLOGY.md`: SPEC.md — источник истины, PROGRESS.md обновлять в конце сессии
- Всё локально, интернет только для разового скачивания модели Whisper (fallback hf-mirror при блокировке)
- Пользователи не разработчики: тексты и ошибки — по-человечески, по-русски
- Версия в 3 местах (updater.py / installer.iss / sidebar) — синхронизировать при релизе; источник правды — git-тег

## Команды
- Запуск локально: `PYTHONPATH=src .venv/bin/python -m steadytranscribe.app`
- Смоук-тест ядра: конвертация + транскрипция, см. PROGRESS.md
- Выкатить версию: `git tag vX.Y.Z && git push origin vX.Y.Z` → Actions собирает установщик → Releases (~10 мин) → у сотрудников автообновление
- Проверить сборку: `gh run watch <id>` ; релиз: `gh release view vX.Y.Z`

---

## Obsidian Knowledge Vault

**Путь к vault:** `/Users/olegkorkin/Downloads/claude/SteadyTranscribe-vault/`

### При старте каждой сессии
1. Прочитай `00-home/index.md` — карта проекта
2. Прочитай `00-home/текущие приоритеты.md` — что в работе
3. Задача про модуль/интеграцию — найди заметку в `knowledge/`

### Как работать во время сессии
- Баг — проверь `knowledge/debugging/` (может уже решали)
- Архитектурное решение — проверь `knowledge/decisions/`
- Интеграция (CI, обновления) — прочитай заметку из `knowledge/integrations/`

### При завершении сессии («сохрани сессию»)
1. `sessions/YYYY-MM-DD-краткое-описание.md` с логом
2. Обнови `00-home/текущие приоритеты.md`
3. Решение → `knowledge/decisions/`; баг → `knowledge/debugging/`; паттерн → `knowledge/patterns/`
4. Обнови `00-home/index.md` при новых важных заметках

### Правила именования
- Названия = утверждения, не категории
- Используй [[wiki-ссылки]] между заметками
