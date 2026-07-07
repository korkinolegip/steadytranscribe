# PyInstaller spec — сборка SteadyTranscribe (onedir)
# Запуск из корня репо: pyinstaller packaging/steadytranscribe.spec
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

block_cipher = None

datas = [("../assets", "assets")]
# КРИТИЧНО: data-файлы faster_whisper (в т.ч. silero_vad_v6.onnx для VAD) —
# без них exe падает при расшифровке. Также данные onnxruntime и sherpa_onnx.
datas += collect_data_files("faster_whisper")
datas += collect_data_files("onnxruntime")
datas += collect_data_files("sherpa_onnx")
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("sherpa_onnx") \
    + collect_dynamic_libs("onnxruntime")

a = Analysis(
    ["../src/run_app.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=["steadytranscribe", "sherpa_onnx", "soundfile", "faster_whisper",
                   "onnxruntime"],
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
    version="version_info.txt",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SteadyTranscribe")
