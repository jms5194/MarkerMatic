import os
import platform
import logger_config


class Updater:
    def __init__(self) -> None:
        self.has_updater_for_platform = False
        self.updater_is_loaded = False
        self.load_updater_if_available()

    def load_updater_if_available(self) -> None:
        """Loads and initializes the updater framework, if one is availabe for the
        current platform, otherwise does nothing."""
        try:
            if platform.system() == "Darwin":
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
                self._updater = SPUStandardUpdaterController.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(  # noqa: F821 # type: ignore
                    True, None, None
                )
                del objc
                self.updater_is_loaded = True
        except Exception as e:
            # Exceptions should never raise, since we want the updater to fail
            # silently, since the app will often be used offline.
            logger_config.logger.error(f"Could not load updater, {e}")

    def check_for_updates(self) -> None:
        try:
            if hasattr(self, "_updater"):
                self._updater.updater().checkForUpdates()
        except Exception as e:
            logger_config.logger.error(f"Could not check for updates, {e}")


if __name__ == "__main__":
    updater = Updater()
    updater.check_for_updates()
