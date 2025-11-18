import os
import platform
import logger_config
import constants


class Updater:
    def __init__(self) -> None:
        self.has_updater_for_platform = False
        self.updater_is_loaded = False
        self.load_updater_if_available()

    def load_updater_if_available(self) -> None:
        """Loads and initializes the updater framework, if one is availabe for the
        current platform, otherwise does nothing."""
        try:
            match platform.system():
                case "Darwin":
                    self.has_updater_for_platform = True
                    py2app_resource_path = os.environ.get("RESOURCEPATH")
                    if py2app_resource_path is None:
                        # We won't load this if we're not in a py2app bundle
                        return

                    import objc

                    path = os.path.join(
                        py2app_resource_path, "..", "Frameworks", "Sparkle.framework"
                    )
                    sparkle_path = objc.pathForFramework(str(path))
                    objc.loadBundle("Sparkle", globals(), bundle_path=sparkle_path)  # pyright: ignore[reportAttributeAccessIssue]
                    self._pyobjc_updater = SPUStandardUpdaterController.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(  # noqa: F821 # type: ignore
                        True, None, None
                    )
                    del objc
                    self.updater_is_loaded = True
                case "Windows":
                    self.has_updater_for_platform = True
                    import pywinsparkle

                    pywinsparkle.win_sparkle_set_app_details(
                        constants.APPLICATION_AUTHOR,
                        constants.APPLICATION_NAME,
                        constants.VERSION_SHORT,
                    )
                    pywinsparkle.win_sparkle_set_appcast_url(
                        constants.SPARKLE_WIN_X64_URL
                    )
                    pywinsparkle.win_sparkle_set_eddsa_public_key(
                        constants.SPARKLE_PUBLIC_ED_KEY
                    )
                    pywinsparkle.win_sparkle_init()
                    self._winsparkle = True
                    self.updater_is_loaded = True
        except Exception as e:
            # Exceptions should never raise, since we want the updater to fail
            # silently, since the app will often be used offline.
            logger_config.logger.error(f"Could not load updater, {e}")

    def check_for_updates(self) -> None:
        try:
            if hasattr(self, "_pyobjc_updater"):
                self._pyobjc_updater.updater().checkForUpdates()
            if hasattr(self, "_winsparkle"):
                import pywinsparkle

                pywinsparkle.win_sparkle_check_update_with_ui()

        except Exception as e:
            logger_config.logger.error(f"Could not check for updates, {e}")

    @property
    def automatically_checks_for_updates(self) -> bool:
        if hasattr(self, "_pyobjc_updater"):
            return bool(self._pyobjc_updater.updater().automaticallyChecksForUpdates())
        elif hasattr(self, "_winsparkle"):
            import pywinsparkle

            return bool(pywinsparkle.win_sparkle_get_automatic_check_for_updates())
        return False

    @automatically_checks_for_updates.setter
    def automatically_checks_for_updates(self, value: bool) -> None:
        if hasattr(self, "_pyobjc_updater"):
            self._pyobjc_updater.updater().setAutomaticallyChecksForUpdates_(value)
        elif hasattr(self, "_winsparkle"):
            import pywinsparkle

            pywinsparkle.win_sparkle_set_automatic_check_for_updates(value)

    @property
    def supports_auto_downloads(self) -> bool:
        if hasattr(self, "_pyobjc_updater"):
            return True
        return False

    @property
    def automatically_downloads_updates(self) -> bool:
        if hasattr(self, "_pyobjc_updater"):
            return bool(self._pyobjc_updater.updater().automaticallyDownloadsUpdates())
        return False

    @automatically_downloads_updates.setter
    def automatically_downloads_updates(self, value: bool) -> None:
        if hasattr(self, "_pyobjc_updater"):
            self._pyobjc_updater.updater().setAutomaticallyDownloadsUpdates_(value)

    def register_request_stop_callback(self, callback: callable) -> None:
        if hasattr(self, "_winsparkle"):
            import pywinsparkle

            pywinsparkle.win_sparkle_set_shutdown_request_callback(callback)

    def stop(self) -> None:
        """Shuts down the updater when the application is shutting down, if
        needed."""
        if hasattr(self, "_winsparkle"):
            import pywinsparkle

            pywinsparkle.win_sparkle_cleanup()


if __name__ == "__main__":
    updater = Updater()
    updater.check_for_updates()
