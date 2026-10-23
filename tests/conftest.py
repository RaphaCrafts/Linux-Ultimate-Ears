"""Isolate Qt settings: Qt caches its config path before XDG changes in tests."""
import pytest
from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def isolated_qt_settings(tmp_path):
    QSettings.setPath(QSettings.NativeFormat,QSettings.UserScope,str(tmp_path))
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(tmp_path))
