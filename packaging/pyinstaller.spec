# -*- mode: python ; coding: utf-8 -*-
import argparse
import os
import sys

import pywinsparkle

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(SPEC), "..")))

import constants

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")

args = parser.parse_args()

datas = [
    (f"../resources/{constants.ICON_WIN_FILENAME}", "./resources"),
    ("../resources/icons", "./resources/icons"),
    (
        "../resources/MarkerMatic-Bridge.bwextension",
        "./resources/MarkerMatic-Bridge.bwextension",
    ),
]


ws_hiddenimports = ["websockets", "websockets.legacy"]
py4j_hiddenimports = ["py4j.java_collections"]
win32com_imports = ["win32com.shell.shell", "win32com.shell.shellcon"]
pywinsparkle_imports = ["pywinsparkle", "pywinsparkle.libs"]

pywinsparkle_binaries = (f"{pywinsparkle.pywinsparkle.DLL_FILE}.dll", ".")

a = Analysis(
    ["../main.py"],
    pathex=[],
    binaries=[pywinsparkle_binaries],
    datas=datas,
    hiddenimports=ws_hiddenimports
    + py4j_hiddenimports
    + win32com_imports
    + pywinsparkle_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=constants.APPLICATION_NAME,
    icon=f"../resources/{constants.ICON_WIN_FILENAME}",
    debug=args.debug is not None and args.debug,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=args.debug is not None and args.debug,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version="pyinstaller_version.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=constants.APPLICATION_NAME,
)
