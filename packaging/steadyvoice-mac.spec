# PyInstaller spec — сборка SteadyVoice для macOS (.app, Apple Silicon)
# Запуск из корня репо: pyinstaller packaging/steadyvoice-mac.spec
#
# Отличия от Windows-спеки (steadytranscribe.spec):
# - ffmpeg/ffprobe кладутся как binaries в подпапку ffmpeg/ — PyInstaller сам
#   собирает их dylib-зависимости (Homebrew-сборка динамическая) и чинит пути;
# - модели диаризации внутрь бандла (в Windows их докладывает CI после сборки);
# - шаг BUNDLE: папка → SteadyVoice.app с Info.plist и иконкой .icns.
# Версию читаем из updater.py — единый источник (сверяется CI-гейтом).
import os
import re
import shutil

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

SPEC_DIR = os.path.dirname(os.path.abspath(SPECPATH)) if os.path.isfile(SPECPATH) else SPECPATH
ROOT = os.path.abspath(os.path.join(SPEC_DIR, ".."))

with open(os.path.join(ROOT, "src/steadytranscribe/ui/updater.py"), encoding="utf-8") as f:
    VERSION = re.search(r'CURRENT_VERSION = "([\d.]+)"', f.read()).group(1)

block_cipher = None

datas = [(os.path.join(ROOT, "assets"), "assets"),
         # frozen-код ищет модели разделения в <ресурсы>/diarization
         (os.path.join(ROOT, "assets/diarization"), "diarization")]
# КРИТИЧНО: data-файлы faster_whisper (в т.ч. silero_vad onnx для VAD) —
# без них сборка падает при расшифровке. Также данные onnxruntime и sherpa_onnx.
datas += collect_data_files("faster_whisper")
datas += collect_data_files("onnxruntime")
datas += collect_data_files("sherpa_onnx")
datas += collect_data_files("certifi")   # корневые сертификаты для HTTPS

binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("sherpa_onnx") \
    + collect_dynamic_libs("onnxruntime")
# ffmpeg/ffprobe: путь передаётся через переменную окружения STEADY_FFMPEG_DIR
# (локально — brew, в CI — каталог со скачанными бинарниками)
_ffdir = os.environ.get("STEADY_FFMPEG_DIR", "/opt/homebrew/bin")
for tool in ("ffmpeg", "ffprobe"):
    src = os.path.join(_ffdir, tool)
    if not os.path.exists(src):
        src = shutil.which(tool)
    if not src:
        raise SystemExit(f"не найден {tool} — установите (brew install ffmpeg) "
                         f"или задайте STEADY_FFMPEG_DIR")
    binaries.append((src, "ffmpeg"))

a = Analysis(
    [os.path.join(ROOT, "src/run_app.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["steadytranscribe", "sherpa_onnx", "soundfile", "faster_whisper",
                   "onnxruntime", "certifi"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    cipher=block_cipher,
)
# модели диаризации нужны только по пути diarization/ (его ждёт frozen-код) —
# копию внутри assets/ выкидываем, это лишние 33 МБ в каждом обновлении
a.datas = [d for d in a.datas if not d[0].startswith(os.path.join("assets", "diarization"))]
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SteadyVoice",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SteadyVoice")
app = BUNDLE(
    coll,
    name="SteadyVoice.app",
    icon=os.path.join(ROOT, "assets/icon.icns"),
    bundle_identifier="com.steadycontrol.steadyvoice",
    info_plist={
        "CFBundleDisplayName": "SteadyVoice",
        "CFBundleName": "SteadyVoice",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        # честный минимум: ffmpeg из Homebrew собран под macOS раннера (14),
        # колёса ctranslate2/PySide6 тоже требуют современную систему
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
        # тёмная тема всегда — рамка окна не станет белой на светлой системе
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "© SteadyControl",
        "LSApplicationCategoryType": "public.app-category.productivity",
    },
)
