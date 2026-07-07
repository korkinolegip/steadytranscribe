# PyInstaller spec — сборка SteadyTranscribe (onedir)
# Запуск из корня репо: pyinstaller packaging/steadytranscribe.spec
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

block_cipher = None

datas = [("../assets", "assets")]
# модели/данные ctranslate2 и sherpa-onnx подтягиваются автоматически из site-packages
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("sherpa_onnx")

a = Analysis(
    ["../src/run_app.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=["steadytranscribe", "sherpa_onnx", "soundfile", "faster_whisper"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SteadyTranscribe",
    console=False,
    icon="../assets/icon.ico",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SteadyTranscribe")
