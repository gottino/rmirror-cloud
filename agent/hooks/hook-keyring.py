"""
PyInstaller hook for keyring module
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('keyring')

# Add keyring backends
hiddenimports += [
    'keyring.backends',
    'keyring.backends.macOS',
    'keyring.backends.OS_X',
]
