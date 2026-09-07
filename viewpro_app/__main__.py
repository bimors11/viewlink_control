import os
from pathlib import Path

from PyQt5 import QtCore

plugins_path = QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.PluginsPath)
os.environ["QT_PLUGIN_PATH"] = plugins_path
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(Path(plugins_path) / "platforms")

from .ui import run


if __name__ == "__main__":
    raise SystemExit(run(Path.cwd()))
