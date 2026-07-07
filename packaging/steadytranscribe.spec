# PyInstaller spec — сборка SteadyTranscribe (onedir)
# Запуск из корня репо: pyinstaller packaging/steadytranscribe.spec
import os

block_cipher = None

a = Analysis(
    ["../src/run_app.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
    hiddenimports=["steadytranscribe"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.f2py"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SteadyTranscribe",
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SteadyTranscribe")
