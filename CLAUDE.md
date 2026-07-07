# SteadyTranscribe — конфиг агента

## Обзор
Windows-приложение (Windows 10/11) локальной транскрипции аудио/видео-файлов для Олега и команды SteadyControl. Воспроизводит функцию File Transcription из FluidVoice (эталон поведения задокументирован в SPEC.md). Всё локально: ffmpeg → faster-whisper. UI на русском.

## Стек
Python 3.12 · PySide6 (Fusion) · faster-whisper (CTranslate2, int8) · ffmpeg (вшит в сборку) · SQLite (история) · PyInstaller + Inno Setup · GitHub Actions (windows-latest)

## Правила
- Работаем по `METHODOLOGY.md` проекта «Обучение»: SPEC.md — источник истины, изменения сначала туда, потом в код; PROGRESS.md обновлять в конце сессии
- Поведение = FluidVoice (стадии прогресса 10/20/30–90/100%, формат экспорта TXT/JSON, лимит истории, пустой текст не сохраняется)
- Пользователь не разработчик: тексты интерфейса и ошибок — по-человечески, по-русски
- Сеть Олега блокирует HuggingFace/Groq по IP — загрузка моделей с fallback на hf-mirror.com обязательна

## Команды
- Запуск локально (мак/винда): `.venv/bin/python -m steadytranscribe.app` из `src/` (или `PYTHONPATH=src python -m steadytranscribe.app`)
- Смоук-тест ядра: конвертация + транскрипция tiny-моделью, см. PROGRESS.md
- Сборка установщика: GitHub Actions `build-windows.yml` (тег `v*` или ручной запуск) → артефакт SteadyTranscribe-Setup
- Локальная сборка на Windows: `pyinstaller packaging/steadytranscribe.spec` + ISCC `packaging/installer.iss`
