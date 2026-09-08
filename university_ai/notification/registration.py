from __future__ import annotations

import logging
import os
import sys
import ctypes
from collections.abc import Callable
from pathlib import Path


# This value is deliberately stable: it is stored in the Start-menu shortcut and
# must be identical to the id passed to ToastNotificationManager.
APP_USER_MODEL_ID = "MillMiya.UniversityAI"


class WindowsToastRegistration:
    """Registers the per-user Start-menu shortcut required by legacy WinRT Toast.

    This is not the logon Startup registration.  The shortcut gives an
    unpackaged desktop application an AppUserModelID identity for Windows Toast.
    """

    def __init__(
        self,
        *,
        shortcut_directory: Path | None = None,
        filename: str = "University AI.lnk",
        app_id: str = APP_USER_MODEL_ID,
        project_root: Path | None = None,
        executable: Path | None = None,
        shortcut_writer: Callable[[Path, str, Path, Path, str], None] | None = None,
        process_identity_setter: Callable[[str], None] | None = None,
    ) -> None:
        default = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
        self._directory = shortcut_directory or default
        self._path = self._directory / filename
        self.app_id = app_id
        self._project_root = project_root or Path(__file__).resolve().parents[2]
        self._executable = executable or Path(sys.executable)
        self._shortcut_writer = shortcut_writer or self._write_shortcut
        self._process_identity_setter = process_identity_setter or self._set_current_process_app_id
        self._registered = False
        self._logger = logging.getLogger(__name__)

    @property
    def shortcut_path(self) -> Path:
        return self._path

    def registered(self) -> bool:
        return self._registered or self._path.is_file()

    def register(self) -> bool:
        """Create or refresh the one stable per-user shortcut idempotently."""
        if self._registered:
            return True
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            self._shortcut_writer(self._path, self.app_id, self._executable, self._project_root, "-m university_ai.app.main")
            self._registered = True
            self._logger.info("Windows Toast shortcut registered at %s", self._path)
            return True
        except (ImportError, OSError, RuntimeError):
            self._logger.exception("Windows Toast shortcut registration failed")
            return False

    def unregister(self) -> bool:
        """Remove only this app's Toast identity shortcut; useful for cleanup/tests."""
        try:
            self._path.unlink()
        except FileNotFoundError:
            self._registered = False
            return True
        except OSError:
            self._logger.exception("Windows Toast shortcut removal failed")
            return False
        self._registered = False
        return True

    def apply_to_current_process(self) -> bool:
        """Give the running unpackaged process the same AUMID before it creates UI."""
        if os.name != "nt":
            return False
        try:
            self._process_identity_setter(self.app_id)
            self._logger.info("Windows Toast process AUMID set to %s", self.app_id)
            return True
        except OSError:
            self._logger.exception("Windows Toast process AUMID setup failed")
            return False

    @staticmethod
    def _set_current_process_app_id(app_id: str) -> None:
        setter = ctypes.WinDLL("shell32").SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        result = setter(app_id)
        if result != 0:
            raise OSError(result, "SetCurrentProcessExplicitAppUserModelID failed")

    @staticmethod
    def _write_shortcut(path: Path, app_id: str, executable: Path, project_root: Path, arguments: str) -> None:
        """Use the Windows Shell IPropertyStore, as required for System.AppUserModel.ID."""
        if os.name != "nt":
            raise RuntimeError("Windows Toast shortcut registration is only available on Windows")
        import pythoncom
        from win32com.shell import shell
        from win32com.propsys import propsys

        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )
        link.SetPath(str(executable))
        link.SetArguments(arguments)
        link.SetWorkingDirectory(str(project_root))
        property_store = link.QueryInterface(propsys.IID_IPropertyStore)
        property_key = propsys.PSGetPropertyKeyFromName("System.AppUserModel.ID")
        property_store.SetValue(property_key, propsys.PROPVARIANTType(app_id))
        property_store.Commit()
        persist_file = link.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Save(str(path), 1)
