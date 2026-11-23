# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for rmirror-core: the headless sync core that rMirror.app
(the native Mac app, docs/native-app-architecture.md) runs as a child process:

    <bundle>/Contents/Resources/core/rmirror-core --headless

onedir, console executable, same entry point as rmirror.spec (app/main.py), but
without the menu bar: rumps (and the PyObjC it pulls in) and app/tray are not
bundled. The legacy rMirror.app keeps using rmirror.spec.

Build:
    poetry run pyinstaller --noconfirm rmirror-core.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

agent_dir = Path(SPECPATH)

hiddenimports = []
datas = []

# Same packages as rmirror.spec, minus rumps
for package in ['click', 'flask', 'watchdog', 'httpx', 'pydantic', 'pydantic_settings', 'keyring']:
    try:
        hiddenimports += collect_submodules(package)
        datas += copy_metadata(package)
    except Exception as e:
        print(f"Warning: Could not collect {package}: {e}")

# Flask templates and static files (sign-in pages, legacy page)
web_datas = [
    (str(agent_dir / 'app' / 'web' / 'templates'), 'app/web/templates'),
    (str(agent_dir / 'app' / 'web' / 'static'), 'app/web/static'),
]

a = Analysis(
    [str(agent_dir / 'app' / 'main.py')],
    pathex=[str(agent_dir)],
    binaries=[],
    datas=web_datas + datas,
    hiddenimports=hiddenimports + [
        'app.watcher.file_watcher',
        'app.sync.cloud_sync',
        'app.sync.queue',
        'app.sync.initial_sync',
        'app.sync.first_run',
        'app.sync.quota_cache',
        'app.remarkable.library',
        'app.web.app',
        'app.web.routes',
        'app.web.routes_v2',
        'app.web.shared',
        'app.updater',
        'app.config',
        'app.logging_config',
        'app.auth.keychain',
        'app.browser_utils',
        'keyring.backends',
        'keyring.backends.macOS',
    ],
    hookspath=[str(agent_dir / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Menu bar: never used in headless mode
        'rumps',
        'app.tray',
        'app.tray.menu_bar',
        'app.tray.status',
        'AppKit',
        'Foundation',
        'objc',
        'PyObjCTools',
        # Dev-only: collect_submodules('pydantic') reaches pydantic.mypy, which would pull in
        # mypy's compiled modules (~5 MB) when mypy is installed in the build environment
        'mypy',
        # Not used
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'tkinter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='rmirror-core',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # stdin/stdout are the parent-watch pipe and the ready line
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='rmirror-core',
)
