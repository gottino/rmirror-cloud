# -*- mode: python ; coding: utf-8 -*-

import re
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# Get the agent directory
agent_dir = Path(SPECPATH)

# Extract version from centralized version module
version_file = agent_dir / 'app' / '__version__.py'
with open(version_file) as f:
    version_match = re.search(r'__version__ = "(.+)"', f.read())
    app_version = version_match.group(1) if version_match else "1.0.0"

block_cipher = None

# Collect all submodules for packages that PyInstaller might miss
hiddenimports = []
datas = []

# Collect all submodules for critical packages
packages_to_collect = ['click', 'flask', 'watchdog', 'httpx', 'pydantic', 'pydantic_settings', 'rumps', 'keyring']
for package in packages_to_collect:
    try:
        hiddenimports += collect_submodules(package)
        datas += copy_metadata(package)
    except Exception as e:
        print(f"Warning: Could not collect {package}: {e}")

# Collect all Flask templates and web UI files
web_datas = [
    (str(agent_dir / 'app' / 'web' / 'templates'), 'app/web/templates'),
    (str(agent_dir / 'app' / 'web' / 'static'), 'app/web/static'),
]

# Collect resources (icons)
resource_datas = [
    (str(agent_dir / 'resources'), 'resources'),
]

a = Analysis(
    [str(agent_dir / 'app' / 'main.py')],
    pathex=[str(agent_dir)],
    binaries=[],
    datas=web_datas + resource_datas + datas,
    hiddenimports=hiddenimports + [
        # App modules
        'app.watcher.file_watcher',
        'app.sync.cloud_sync',
        'app.sync.queue',
        'app.web.app',
        'app.web.routes',
        'app.tray.menu_bar',
        'app.config',
        'app.logging_config',
        'app.auth.keychain',
        'app.browser_utils',
        # Keyring backends
        'keyring.backends',
        'keyring.backends.macOS',
        'keyring.backends.OS_X',
    ],
    hookspath=[str(agent_dir / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='rMirror',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
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
    upx=True,
    upx_exclude=[],
    name='rMirror',
)

app = BUNDLE(
    coll,
    name='rMirror.app',
    icon=str(agent_dir / 'build' / 'icon.icns'),
    bundle_identifier='io.rmirror.agent',
    info_plist={
        'CFBundleDisplayName': 'rMirror',
        'CFBundleShortVersionString': app_version,
        'CFBundleVersion': app_version,
        'LSMinimumSystemVersion': '12.0',
        'LSUIElement': True,  # Run as background app (no Dock icon)
        'NSHighResolutionCapable': True,
        'NSHumanReadableCopyright': 'Copyright © 2024 rMirror Cloud. All rights reserved.',
        'LSApplicationCategoryType': 'public.app-category.productivity',
    },
)
