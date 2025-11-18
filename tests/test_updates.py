# tests/test_updates.py
import types
import sys

import updates
import constants


def test_load_updater_if_available_darwin_not_in_py2app(monkeypatch):
    """On macOS without RESOURCEPATH set, updater shouldn't be loaded."""
    # Ensure RESOURCEPATH is not set
    monkeypatch.delenv("RESOURCEPATH", raising=False)
    # Patch the platform used inside updates.py
    monkeypatch.setattr("updates.platform.system", lambda: "Darwin")

    updater = updates.Updater()

    assert updater.has_updater_for_platform is True
    assert updater.updater_is_loaded is False
    assert not hasattr(updater, "_pyobjc_updater")


def test_load_updater_if_available_non_supported_platform(monkeypatch):
    """On non‑Darwin, non‑Windows platforms, no updater should be available."""
    monkeypatch.setattr("updates.platform.system", lambda: "Linux")

    updater = updates.Updater()

    assert updater.has_updater_for_platform is False
    assert updater.updater_is_loaded is False
    assert not hasattr(updater, "_pyobjc_updater")
    assert not hasattr(updater, "_winsparkle")


def test_load_updater_if_available_windows_initializes_winsparkle(monkeypatch):
    """On Windows, Updater should call win_sparkle_init and mark itself loaded."""
    monkeypatch.setattr("updates.platform.system", lambda: "Windows")

    # Create a fake pywinsparkle module
    fake_pywinsparkle = types.SimpleNamespace()
    calls = {
        "set_app_details": None,
        "set_appcast_url": None,
        "set_eddsa_key": None,
        "init_called": False,
    }

    def win_sparkle_set_app_details(company_name, app_name, app_version):
        calls["set_app_details"] = (company_name, app_name, app_version)

    def win_sparkle_set_appcast_url(url):
        calls["set_appcast_url"] = url

    def win_sparkle_set_eddsa_public_key(key):
        calls["set_eddsa_key"] = key

    def win_sparkle_init():
        calls["init_called"] = True

    fake_pywinsparkle.win_sparkle_set_app_details = win_sparkle_set_app_details
    fake_pywinsparkle.win_sparkle_set_appcast_url = win_sparkle_set_appcast_url
    fake_pywinsparkle.win_sparkle_set_eddsa_public_key = win_sparkle_set_eddsa_public_key
    fake_pywinsparkle.win_sparkle_init = win_sparkle_init

    monkeypatch.setitem(sys.modules, "pywinsparkle", fake_pywinsparkle)

    updater = updates.Updater()

    assert updater.has_updater_for_platform is True
    assert updater.updater_is_loaded is True
    assert hasattr(updater, "_winsparkle")

    # Verify that the expected WinSparkle configuration calls were made
    assert calls["set_app_details"] == (
        constants.APPLICATION_AUTHOR,
        constants.APPLICATION_NAME,
        constants.VERSION_SHORT,
    )
    assert calls["set_appcast_url"] == constants.SPARKLE_WIN_X64_URL
    assert calls["set_eddsa_key"] == constants.SPARKLE_PUBLIC_ED_KEY
    assert calls["init_called"] is True


def test_check_for_updates_calls_pyobjc_updater(monkeypatch):
    """check_for_updates should call the underlying pyobjc updater if present."""

    # Avoid running real load_updater_if_available
    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    # Fake pyobjc updater object
    class FakeUpdaterObj:
        def __init__(self):
            self.check_called = False

        def checkForUpdates(self):
            self.check_called = True

    class FakePyObjcController:
        def __init__(self):
            self._updater_obj = FakeUpdaterObj()

        def updater(self):
            return self._updater_obj

    updater = updates.Updater()
    updater._pyobjc_updater = FakePyObjcController()

    updater.check_for_updates()

    assert updater._pyobjc_updater._updater_obj.check_called is True


def test_check_for_updates_calls_winsparkle(monkeypatch):
    """check_for_updates should call WinSparkle when _winsparkle is present."""
    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    fake_pywinsparkle = types.SimpleNamespace()
    called = {"check_update": False}

    def win_sparkle_check_update_with_ui():
        called["check_update"] = True

    fake_pywinsparkle.win_sparkle_check_update_with_ui = win_sparkle_check_update_with_ui
    monkeypatch.setitem(sys.modules, "pywinsparkle", fake_pywinsparkle)

    updater = updates.Updater()
    updater._winsparkle = True  # simulate Windows setup

    updater.check_for_updates()

    assert called["check_update"] is True


def test_automatically_checks_for_updates_getter_and_setter_pyobjc(monkeypatch):
    """Getter and setter should proxy to the underlying pyobjc updater."""

    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    class FakeUpdaterObj:
        def __init__(self):
            self._auto = False

        def automaticallyChecksForUpdates(self):
            return self._auto

        def setAutomaticallyChecksForUpdates_(self, value):
            self._auto = bool(value)

    class FakePyObjcController:
        def __init__(self):
            self._updater_obj = FakeUpdaterObj()

        def updater(self):
            return self._updater_obj

    updater = updates.Updater()
    updater._pyobjc_updater = FakePyObjcController()

    # Default should be False
    assert updater.automatically_checks_for_updates is False

    updater.automatically_checks_for_updates = True
    assert updater.automatically_checks_for_updates is True


def test_automatically_checks_for_updates_getter_and_setter_winsparkle(monkeypatch):
    """Getter and setter should proxy to the WinSparkle functions when available."""
    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    fake_pywinsparkle = types.SimpleNamespace()
    state = {"value": False}

    def win_sparkle_get_automatic_check_for_updates():
        return state["value"]

    def win_sparkle_set_automatic_check_for_updates(v):
        state["value"] = bool(v)

    fake_pywinsparkle.win_sparkle_get_automatic_check_for_updates = (
        win_sparkle_get_automatic_check_for_updates
    )
    fake_pywinsparkle.win_sparkle_set_automatic_check_for_updates = (
        win_sparkle_set_automatic_check_for_updates
    )
    monkeypatch.setitem(sys.modules, "pywinsparkle", fake_pywinsparkle)

    updater = updates.Updater()
    updater._winsparkle = True

    assert updater.automatically_checks_for_updates is False

    updater.automatically_checks_for_updates = True
    assert updater.automatically_checks_for_updates is True
    assert state["value"] is True


def test_supports_auto_downloads_only_when_pyobjc(monkeypatch):
    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    updater = updates.Updater()
    assert updater.supports_auto_downloads is False

    # Simulate pyobjc updater
    updater._pyobjc_updater = object()
    assert updater.supports_auto_downloads is True


def test_automatically_downloads_updates_proxy(monkeypatch):
    """Getter/setter for auto downloads should proxy to pyobjc updater when present."""

    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    class FakeUpdaterObj:
        def __init__(self):
            self._auto_download = False

        def automaticallyDownloadsUpdates(self):
            return self._auto_download

        def setAutomaticallyDownloadsUpdates_(self, value):
            self._auto_download = bool(value)

    class FakePyObjcController:
        def __init__(self):
            self._updater_obj = FakeUpdaterObj()

        def updater(self):
            return self._updater_obj

    updater = updates.Updater()
    updater._pyobjc_updater = FakePyObjcController()

    assert updater.automatically_downloads_updates is False
    updater.automatically_downloads_updates = True
    assert updater.automatically_downloads_updates is True


def test_register_request_stop_callback_winsparkle(monkeypatch):
    """register_request_stop_callback should hook the given callback into WinSparkle."""

    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    fake_pywinsparkle = types.SimpleNamespace()
    recorded_callback = {"value": None}

    def win_sparkle_set_shutdown_request_callback(cb):
        recorded_callback["value"] = cb

    fake_pywinsparkle.win_sparkle_set_shutdown_request_callback = (
        win_sparkle_set_shutdown_request_callback
    )
    monkeypatch.setitem(sys.modules, "pywinsparkle", fake_pywinsparkle)

    updater = updates.Updater()
    updater._winsparkle = True

    def dummy_callback():
        return None

    updater.register_request_stop_callback(dummy_callback)

    assert recorded_callback["value"] is dummy_callback


def test_stop_cleans_up_winsparkle(monkeypatch):
    """stop() should call WinSparkle cleanup when available."""

    monkeypatch.setattr(updates.Updater, "load_updater_if_available", lambda self: None)

    fake_pywinsparkle = types.SimpleNamespace()
    called = {"cleanup": False}

    def win_sparkle_cleanup():
        called["cleanup"] = True

    fake_pywinsparkle.win_sparkle_cleanup = win_sparkle_cleanup
    monkeypatch.setitem(sys.modules, "pywinsparkle", fake_pywinsparkle)

    updater = updates.Updater()
    updater._winsparkle = True

    updater.stop()

    assert called["cleanup"] is True