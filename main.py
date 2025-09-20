import ipaddress
import os.path
import platform
import threading
import webbrowser
from typing import Collection, Optional

import wx
import wx.adv
import wx.lib.buttons
import wx.svg
import wx.svg._nanosvg
from pubsub import pub

import constants
import ui
import utilities
from app_settings import settings
from consoles import CONSOLES, Console, Feature
from constants import PlaybackState, PyPubSubTopics
from daws import Daw
import external_control
from logger_config import logger
from utilities import DawConsoleBridge

HALF_INTERNAL_SPACING = 5
INTERNAL_SPACING = 10
EXTERNAL_SPACING = 15

LABEL_ROW = 1


class MainWindow(wx.Frame):
    # Bringing the logic from utilities as an attribute of MainWindow
    BridgeFunctions = DawConsoleBridge()
    _app_icons: wx.IconBundle

    def __init__(self):
        logger.info("Initializing main window")
        wx.Frame.__init__(
            self,
            parent=None,
            title=constants.APPLICATION_NAME,
            style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX),
        )

        MainPanel(self)
        self.SetPosition(settings.window_loc)
        self.Fit()

        self.SetIcons(self.get_app_icons())

        menu_bar = wx.MenuBar()
        if platform.system() == "Darwin":
            main_menu = menu_bar.OSXGetAppleMenu()
            self.Bind(wx.EVT_MENU, self.on_close, main_menu.FindItemById(wx.ID_EXIT))
        else:
            main_menu = wx.Menu()
        preferences_menuitem = main_menu.Prepend(wx.ID_PREFERENCES)
        if platform.system() == "Darwin":
            main_menu.PrependSeparator()
            about_menuitem = main_menu.Prepend(wx.ID_ABOUT)
        else:
            main_menu.AppendSeparator()
            menu_exit = main_menu.Append(wx.ID_EXIT)
            self.Bind(wx.EVT_MENU, self.on_close, menu_exit)
            menu_bar.Append(main_menu, "&File")
        help_menu = wx.Menu()
        if platform.system() != "Darwin":
            about_menuitem = help_menu.Prepend(wx.ID_ABOUT)
            help_menu.AppendSeparator()
        documentation_menuitem = help_menu.Append(wx.ID_ANY, "&Documentation")
        help_menu.AppendSeparator()
        license_menuitem = help_menu.Append(wx.ID_ANY, "&License && Thanks")
        menu_bar.Append(help_menu, "&Help")

        self.SetMenuBar(menu_bar)

        # Main Window Bindings
        self.Bind(wx.EVT_MENU, self.on_about, about_menuitem)
        self.Bind(wx.EVT_MENU, self.on_documentation, documentation_menuitem)
        self.Bind(wx.EVT_MENU, self.on_license, license_menuitem)
        self.Bind(wx.EVT_MENU, self.on_preferences, preferences_menuitem)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        pub.subscribe(
            wx.CallAfter,
            PyPubSubTopics.UPDATE_MAIN_WINDOW_DISPLAY_SETTINGS,
            callableObj=self.update_display_settings,
        )
        self.update_display_settings()

        self.Show()

    def on_about(self, _) -> None:
        """Show the About dialog"""
        info = wx.adv.AboutDialogInfo()
        info.SetVersion(constants.VERSION)
        info.SetCopyright(constants.APPLICATION_COPYRIGHT)
        wx.adv.AboutBox(info, self)

    def on_documentation(self, _) -> None:
        """Launch the documentation page in the user's web browser"""
        webbrowser.open(constants.WEBSITE_DOCUMENTATION)

    def on_license(self, _) -> None:
        """Launch the license page in the user's web browser"""
        webbrowser.open(constants.WEBSITE_LICENSE)

    def on_preferences(self, _: Optional[wx.CommandEvent] = None):
        """Launch the preferences window, if it's not visible.
        Otherwise bring it to the front"""
        if hasattr(self, "_preferences_window"):
            try:
                self._preferences_window.Raise()
            except RuntimeError:
                # If the preferences window was previously closed
                del self._preferences_window
                self.on_preferences()
        else:
            self._preferences_window = PrefsWindow(
                parent=wx.GetTopLevelParent(self),
                title=f"{constants.APPLICATION_NAME} Preferences",
                console=self.BridgeFunctions.console,
                icons=self.get_app_icons(),
            )

    def on_close(self, event: wx.CloseEvent | wx.CommandEvent):
        """Handle application shutdown requests from the UI,
        and prompt to confirm if we're able to"""
        cur_pos = self.GetTopLevelParent().GetPosition()
        self.BridgeFunctions.update_pos_in_config(cur_pos)

        if isinstance(event, wx.CommandEvent) or event.CanVeto():
            logger.info("Confirming if the user would like to close")
            dlg = wx.MessageDialog(
                self,
                f"Do you really want to close {constants.APPLICATION_NAME}?",
                "Confirm Exit",
                wx.OK | wx.CANCEL | wx.ICON_QUESTION,
            )
            result = dlg.ShowModal()
            dlg.Destroy()
            if result != wx.ID_OK:
                if isinstance(event, wx.CloseEvent):
                    event.Veto()
                return
        closed_complete = self.BridgeFunctions.close_servers()
        if closed_complete:
            try:
                self.GetTopLevelParent().Destroy()
            except Exception as e:
                logger.error(f"Error closing application: {e}")

    def update_display_settings(self) -> None:
        if settings.always_on_top:
            self.SetWindowStyle(self.GetWindowStyle() | wx.STAY_ON_TOP)
        else:
            self.SetWindowStyle(self.GetWindowStyle() & ~wx.STAY_ON_TOP)

    def get_app_icons(self) -> wx.IconBundle:
        if not hasattr(self, "_app_icon"):
            self._app_icons = wx.IconBundle(
                os.path.abspath(
                    os.path.join(
                        utilities.get_resources_directory_path(),
                        constants.ICON_WIN_FILENAME,
                    )
                ),
                wx.BITMAP_TYPE_ICO,
            )
        return self._app_icons


class MainPanel(wx.Window):
    console_timeout_timer: Optional[wx.CallLater] = None

    def __init__(self, parent):
        logger.info("Initializing main panel")
        super().__init__(parent)
        header_font = wx.Font().Bold()
        header_font.MakeLarger()
        header_font.MakeLarger()

        panel_sizer = wx.FlexGridSizer(
            cols=1, gap=wx.Size(INTERNAL_SPACING, EXTERNAL_SPACING)
        )

        console_header = wx.StaticText(
            self, label=f"{constants.APPLICATION_NAME} Mode", style=wx.ALIGN_CENTER
        )
        console_header.SetFont(header_font)
        panel_sizer.Add(console_header, flag=wx.EXPAND)

        # Button grid for application mode
        mode_grid = wx.GridSizer(5, wx.Size(INTERNAL_SPACING, INTERNAL_SPACING))
        self.mode_record_button = ui.NoBorderBitmapToggle(
            self, playback_state=PlaybackState.RECORDING
        )
        self.mode_record_button.SetToolTip("Recording")
        self.mode_playbacktracking_button = ui.NoBorderBitmapToggle(
            self, playback_state=PlaybackState.PLAYBACK_TRACK
        )
        self.mode_playbacktracking_button.SetToolTip("Playback Tracking")
        self.mode_playbacknotrack_button = ui.NoBorderBitmapToggle(
            self, playback_state=PlaybackState.PLAYBACK_NO_TRACK
        )
        self.mode_playbacknotrack_button.SetToolTip("Playback No Track")
        self._mode_buttons: Collection[ui.NoBorderBitmapToggle] = (
            self.mode_record_button,
            self.mode_playbacktracking_button,
            self.mode_playbacknotrack_button,
        )
        for button in self._mode_buttons:
            mode_grid.Add(button, flag=wx.EXPAND)

        marker_button = ui.NoBorderBitmapButton(self, icon="marker")
        marker_button.SetToolTip("Drop Marker")
        mode_grid.Add(marker_button, flag=wx.EXPAND)

        attempt_reconnect_button = ui.NoBorderBitmapButton(self, icon="reconnect")
        attempt_reconnect_button.SetToolTip("Attempt Reconnect")
        self.Bind(
            wx.EVT_BUTTON,
            attempt_reconnect,
            attempt_reconnect_button,
        )
        mode_grid.Add(attempt_reconnect_button, flag=wx.EXPAND)

        panel_sizer.Add(mode_grid, flag=wx.EXPAND)

        panel_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND,
        )

        connection_statuses_grid = wx.FlexGridSizer(
            cols=2, vgap=INTERNAL_SPACING, hgap=INTERNAL_SPACING
        )

        self.console_connection_icon = ui.ToggleableStaticBitmap(
            self,
            icon_name="connection",
            size=wx.Size(24, 24),
        )
        connection_statuses_grid.Add(
            self.console_connection_icon, flag=wx.ALIGN_CENTRE_VERTICAL
        )

        self.console_connection_label = wx.StaticText(self)
        self.update_console_connection_status()
        connection_statuses_grid.Add(
            self.console_connection_label, flag=wx.ALIGN_CENTRE_VERTICAL
        )

        self.daw_connection_icon = ui.ToggleableStaticBitmap(
            self,
            icon_name="connection",
            size=wx.Size(24, 24),
        )
        connection_statuses_grid.Add(
            self.daw_connection_icon, flag=wx.ALIGN_CENTRE_VERTICAL
        )

        self.daw_connection_label = wx.StaticText(self)
        self.update_daw_connection_status()
        connection_statuses_grid.Add(
            self.daw_connection_label, flag=wx.ALIGN_CENTRE_VERTICAL
        )

        panel_sizer.Add(connection_statuses_grid, flag=wx.EXPAND)

        # External border
        external_border_sizer = wx.BoxSizer()
        external_border_sizer.Add(
            panel_sizer, flag=wx.EXPAND | wx.ALL, border=EXTERNAL_SPACING
        )
        self.SetSizer(external_border_sizer)
        self.Fit()
        # Bindings
        self.Bind(wx.EVT_BUTTON, self.place_marker, marker_button)
        for button in self._mode_buttons:
            self.Bind(
                wx.EVT_BUTTON,
                self._mode_button_pressed,
                button,
            )
            self.Bind(
                wx.EVT_TOGGLEBUTTON,
                self._mode_button_pressed,
                button,
            )
        # Set Playback Tracking as the default state
        self.mode_playbacktracking_button.SetValue(True)
        # Subscribing to the OSC response for console name to reset the timeout timer
        pub.subscribe(self.console_connected, PyPubSubTopics.CONSOLE_CONNECTED)
        pub.subscribe(
            self.console_disconnected,
            PyPubSubTopics.CONSOLE_DISCONNECTED,
        )
        pub.subscribe(
            self.update_daw_connection_status, PyPubSubTopics.DAW_CONNECTION_STATUS
        )
        pub.subscribe(self.call_for_daw_reset, PyPubSubTopics.REQUEST_DAW_RESTART)
        pub.subscribe(self.update_mode_select, PyPubSubTopics.CHANGE_PLAYBACK_STATE)
        MainWindow.BridgeFunctions.start_threads()
        # Start a timer for console timeout
        self.timer_lock = threading.Lock()
        self.configure_timers()

    def _mode_button_pressed(self, event: wx.CommandEvent) -> None:
        for button in self._mode_buttons:
            if button is event.GetEventObject() and event.IsChecked():
                button.Disable()
                if button.playback_state in PlaybackState:
                    logger.info(f"marker_mode set to {button.playback_state}")
                    settings.marker_mode = button.playback_state
            else:
                button.Enable()
                button.SetValue(False)

    @staticmethod
    def place_marker(e):
        # Manually places a marker from the UI
        pub.sendMessage(
            PyPubSubTopics.PLACE_MARKER_WITH_NAME, marker_name="Marker from UI"
        )

    def update_mode_select(self, selected_mode: PlaybackState):
        if selected_mode is PlaybackState.RECORDING:
            wx.CallAfter(self.mode_record_button.SetValue, True)
        elif selected_mode is PlaybackState.PLAYBACK_TRACK:
            wx.CallAfter(self.mode_playbacktracking_button.SetValue, True)
        elif selected_mode is PlaybackState.PLAYBACK_NO_TRACK:
            wx.CallAfter(self.mode_playbacknotrack_button.SetValue, True)

    def configure_timers(self):
        # Builds a 5-second non-blocking timer for console response timeout.
        # Calls self.console_disconnected if timer runs out.
        with self.timer_lock:

            def safe_timer_config():
                if (
                    self.console_timeout_timer
                    and self.console_timeout_timer.IsRunning()
                ):
                    self.console_timeout_timer.Stop()
                self.console_timeout_timer = wx.CallLater(
                    5000, self.update_console_connection_status, connected=False
                )
                self.console_timeout_timer.Start()

            wx.CallAfter(safe_timer_config)

    def update_console_connection_status(
        self,
        connected: bool = False,
        console_name: Optional[str] = None,
        console: Optional[Console] = None,
    ) -> None:
        if console is None:
            console = MainWindow.BridgeFunctions.console
        if connected is not None:
            self.console_connection_icon.set_state(connected)
        if connected:
            if console_name is not None:
                self._console_name = console_name
            if self._console_name is not None:
                console_name_str = f"{self._console_name} "
            else:
                console_name_str = str()
            self.console_connection_label.SetLabel(
                f"{console.type} {console_name_str}is connected"
            )
        else:
            self._console_name = None
            self.console_connection_label.SetLabel(f"{console.type} is not connected")

    def update_daw_connection_status(
        self,
        connected: bool = False,
        daw: Optional[Daw] = None,
    ) -> None:
        if daw is None:
            daw = MainWindow.BridgeFunctions.daw
        if connected:
            wx.CallAfter(self.daw_connection_icon.set_state, True)
            wx.CallAfter(self.daw_connection_label.SetLabel, f"{daw.type} is connected")
        else:
            wx.CallAfter(self.daw_connection_icon.set_state, False)
            wx.CallAfter(
                self.daw_connection_label.SetLabel, f"{daw.type} is not connected"
            )

    def console_connected(self, consolename: Optional[str] = None):
        if (
            isinstance(self.console_timeout_timer, wx.CallLater)
            and self.console_timeout_timer.IsRunning()
        ):
            wx.CallAfter(self.console_timeout_timer.Stop)
        self.configure_timers()
        wx.CallAfter(self.update_console_connection_status, True, consolename)

    def console_disconnected(self) -> None:
        wx.CallAfter(self.update_console_connection_status, connected=False)

    def call_for_daw_reset(self, daw_name: str):
        logger.info(f"{daw_name} has been auto configured. Requesting restart")

        def inner(daw_name):
            dlg = wx.MessageDialog(
                self,
                f"{daw_name} has been configured for use with {constants.APPLICATION_NAME}.\n"
                f"Please restart {daw_name} and press OK",
                f"{daw_name} Configured",
                wx.OK | wx.ICON_QUESTION,
            )
            dlg.ShowModal()
            dlg.Destroy()

        wx.CallAfter(inner, daw_name)


def attempt_reconnect(_: wx.Event):
    """Handles the wxPython event, and calls the actual attempt_reconnect function"""
    MainWindow.BridgeFunctions.attempt_reconnect()


class PrefsWindow(wx.Frame):
    # This is our preferences window pane
    def __init__(self, title, parent, console: Console, icons: wx.IconBundle):
        logger.info("Creating PrefsWindow")
        wx.Frame.__init__(
            self,
            parent=parent,
            title=title,
            style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX),
        )
        PrefsPanel(self, console=console)
        self.Fit()
        if self.GetSize().Width < 300:
            self.SetSize(width=300, height=-1)
        self.SetIcons(icons)
        self.Show()


class PrefsPanel(wx.Panel):
    def __init__(self, parent, console: Console):
        logger.info("Creating PrefsPanel")
        wx.Panel.__init__(self, parent)
        # Define Fonts:
        self.ip_inspected = False
        panel_sizer = wx.BoxSizer(wx.VERTICAL)

        header_font = wx.Font().Bold()
        header_font.MakeLarger()
        header_font.MakeLarger()

        item_font = wx.Font()
        item_font.SetWeight(wx.FONTWEIGHT_MEDIUM)
        item_font.MakeLarger()

        port_font = wx.Font()
        port_font.SetWeight(wx.FONTWEIGHT_LIGHT)
        port_font.MakeSmaller()

        # Console Section
        panel_sizer.AddSpacer(EXTERNAL_SPACING)
        console_header = wx.StaticText(self, label="Console", style=wx.ALIGN_CENTER)
        console_header.SetFont(header_font)
        panel_sizer.Add(
            console_header, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=EXTERNAL_SPACING
        )
        panel_sizer.AddSpacer(HALF_INTERNAL_SPACING)
        panel_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)
        console_main_section = wx.FlexGridSizer(2, INTERNAL_SPACING, INTERNAL_SPACING)
        console_main_section.AddGrowableCol(1)
        console_main_section.SetFlexibleDirection(direction=wx.HORIZONTAL)
        # Console Type
        console_main_section.Add(
            wx.StaticText(self, label="Type:", style=wx.ALIGN_RIGHT)
        )
        console_types = list(CONSOLES)
        console_types.sort()
        self.console_type_choice = wx.Choice(self, choices=console_types)
        try:
            self.console_type_choice.SetSelection(
                console_types.index(settings.console_type)
            )
        except ValueError:
            logger.error("Tried to load a console that isn't available")
        console_main_section.Add(
            self.console_type_choice, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        # Console IP
        console_ip_label = wx.StaticText(
            self, label="IP address:", style=wx.ALIGN_RIGHT
        )
        console_main_section.Add(console_ip_label)
        self.console_ip_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.console_ip_control.SetMaxLength(15)
        self.console_ip_control.SetValue(settings.console_ip)
        console_main_section.Add(
            self.console_ip_control, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        # label_min_width is used to force FlexSizers with only a checkbox (so no label) to look right
        label_min_width = console_ip_label.GetBestSize().width
        # Console Ports
        console_main_section.AddStretchSpacer()
        console_main_ports_label_section = wx.GridSizer(1, 2, 0, INTERNAL_SPACING)
        console_main_send_label = wx.StaticText(self, label="Send")
        console_main_send_label.SetFont(port_font)
        console_main_ports_label_section.Add(
            console_main_send_label, flag=wx.ALIGN_BOTTOM | wx.ALIGN_CENTER_HORIZONTAL
        )
        console_main_receive_label = wx.StaticText(self, label="Receive")
        console_main_receive_label.SetFont(port_font)
        console_main_ports_label_section.Add(
            console_main_receive_label,
            flag=wx.ALIGN_BOTTOM | wx.ALIGN_CENTER_HORIZONTAL,
        )
        console_main_section.Add(
            console_main_ports_label_section, flag=wx.EXPAND, userData=LABEL_ROW
        )
        console_main_section.Add(
            wx.StaticText(self, label="Ports:", style=wx.ALIGN_RIGHT)
        )
        console_main_ports_section = wx.GridSizer(1, 2, 0, INTERNAL_SPACING)
        self.console_send_port_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.console_send_port_control.SetMaxLength(5)
        self.console_send_port_control.SetValue(str(settings.console_port))
        console_main_ports_section.Add(
            self.console_send_port_control, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        self.console_rcv_port_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.console_rcv_port_control.SetMaxLength(5)
        self.console_rcv_port_control.SetValue(str(settings.receive_port))
        console_main_ports_section.Add(
            self.console_rcv_port_control, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        console_main_section.Add(console_main_ports_section, flag=wx.EXPAND)
        panel_sizer.Add(
            console_main_section,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)

        # Console Repeater Section
        panel_sizer.AddSpacer(INTERNAL_SPACING)
        panel_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)
        console_repeater_section = wx.FlexGridSizer(
            2, INTERNAL_SPACING, INTERNAL_SPACING
        )
        console_repeater_section.AddGrowableCol(1)
        console_repeater_section.SetFlexibleDirection(direction=wx.HORIZONTAL)
        console_repeater_section.AddStretchSpacer()
        # Repeater Enabled
        self.repeater_radio_enabled = wx.CheckBox(self, label="Repeater enabled")
        self.repeater_radio_enabled.SetValue(settings.forwarder_enabled)
        console_repeater_section.Add(self.repeater_radio_enabled, flag=wx.EXPAND)
        # Repeater IP
        console_repeater_section.Add(
            wx.StaticText(self, label="Tablet IP:", style=wx.ALIGN_RIGHT)
        )
        self.repeater_ip_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.repeater_ip_control.SetMaxLength(15)
        self.repeater_ip_control.SetValue(settings.repeater_ip)
        console_repeater_section.Add(
            self.repeater_ip_control, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        # Repeater Ports
        console_repeater_section.AddStretchSpacer()
        console_repeater_ports_label_section = wx.GridSizer(1, 2, 0, INTERNAL_SPACING)
        console_send_label = wx.StaticText(self, label="Send")
        console_send_label.SetFont(port_font)
        console_repeater_ports_label_section.Add(
            console_send_label, flag=wx.ALIGN_BOTTOM | wx.ALIGN_CENTER_HORIZONTAL
        )
        console_receive_label = wx.StaticText(self, label="Receive")
        console_receive_label.SetFont(port_font)
        console_repeater_ports_label_section.Add(
            console_receive_label, flag=wx.ALIGN_BOTTOM | wx.ALIGN_CENTER_HORIZONTAL
        )
        console_repeater_section.Add(
            console_repeater_ports_label_section, flag=wx.EXPAND, userData=LABEL_ROW
        )
        console_repeater_section.Add(
            wx.StaticText(self, label="Ports:", style=wx.ALIGN_RIGHT)
        )
        console_repeater_ports_section = wx.GridSizer(1, 2, 0, INTERNAL_SPACING)
        self.repeater_send_port_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.repeater_send_port_control.SetMaxLength(5)
        self.repeater_send_port_control.SetValue(str(settings.repeater_port))
        console_repeater_ports_section.Add(
            self.repeater_send_port_control, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        self.repeater_rcv_port_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.repeater_rcv_port_control.SetMaxLength(5)
        self.repeater_rcv_port_control.SetValue(str(settings.repeater_receive_port))
        console_repeater_ports_section.Add(
            self.repeater_rcv_port_control, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL
        )
        console_repeater_section.Add(console_repeater_ports_section, flag=wx.EXPAND)
        panel_sizer.Add(
            console_repeater_section,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)

        # DAW Section
        daw_header = wx.StaticText(self, label="DAW", style=wx.ALIGN_CENTER)
        daw_header.SetFont(header_font)
        panel_sizer.Add(
            daw_header, flag=wx.LEFT | wx.RIGHT | wx.EXPAND, border=EXTERNAL_SPACING
        )
        panel_sizer.AddSpacer(HALF_INTERNAL_SPACING)
        panel_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)
        daw_section = wx.FlexGridSizer(2, INTERNAL_SPACING, INTERNAL_SPACING)
        daw_section.AddGrowableCol(1)
        daw_section.SetFlexibleDirection(direction=wx.HORIZONTAL)
        daw_section.Add(wx.StaticText(self, label="Type:", style=wx.ALIGN_RIGHT))
        # DAW Type
        daw_types = [daw.type for daw in Daw.__subclasses__()]
        daw_types.sort()
        self.daw_type_choice = wx.Choice(self, choices=daw_types)
        try:
            self.daw_type_choice.SetSelection(daw_types.index(settings.daw_type))
        except ValueError:
            logger.error("Tried to load a DAW that isn't available")
        daw_section.Add(self.daw_type_choice, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        panel_sizer.Add(
            daw_section,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)

        # Application Settings Section
        application_header = wx.StaticText(
            self, label="Application", style=wx.ALIGN_CENTER
        )
        application_header.SetFont(header_font)
        panel_sizer.Add(
            application_header,
            flag=wx.LEFT | wx.RIGHT | wx.EXPAND,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(HALF_INTERNAL_SPACING)
        panel_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)
        app_settings_section = wx.FlexGridSizer(2, INTERNAL_SPACING, INTERNAL_SPACING)
        app_settings_section.AddGrowableCol(1)
        app_settings_section.SetFlexibleDirection(direction=wx.VERTICAL)
        # Always On Top
        app_settings_section.Add(width=label_min_width, height=0)
        self.always_on_top_checkbox = wx.CheckBox(self, label="Always display on top")
        self.always_on_top_checkbox.SetValue(settings.always_on_top)
        app_settings_section.Add(self.always_on_top_checkbox, flag=wx.EXPAND)
        # Only match cue name
        app_settings_section.AddStretchSpacer()
        self.match_mode_label_only = wx.CheckBox(self, label="Only match cue name")
        app_settings_section.Add(self.match_mode_label_only, flag=wx.EXPAND)
        self.match_mode_label_only.SetValue(settings.name_only_match)
        panel_sizer.Add(
            app_settings_section,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)

        # External Control Section
        external_control_header = wx.StaticText(
            self, label="External Control", style=wx.ALIGN_CENTER
        )
        external_control_header.SetFont(header_font)
        panel_sizer.Add(
            external_control_header,
            flag=wx.LEFT | wx.RIGHT | wx.EXPAND,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(HALF_INTERNAL_SPACING)
        panel_sizer.Add(
            wx.StaticLine(self),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=EXTERNAL_SPACING,
        )
        panel_sizer.AddSpacer(INTERNAL_SPACING)
        external_control_section = wx.FlexGridSizer(
            2, INTERNAL_SPACING, INTERNAL_SPACING
        )
        external_control_section.AddGrowableCol(1)
        external_control_section.SetFlexibleDirection(direction=wx.VERTICAL)
        # External Control OSC Port
        external_control_section.Add(
            wx.StaticText(self, label="OSC port:", style=wx.ALIGN_RIGHT)
        )
        self.external_control_osc_port_control = wx.TextCtrl(self, style=wx.TE_CENTER)
        self.external_control_osc_port_control.SetMaxLength(5)
        self.external_control_osc_port_control.SetValue(
            str(settings.external_control_osc_port)
        )
        external_control_section.Add(
            self.external_control_osc_port_control,
            flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL,
        )
        self.external_control_osc_port_control.SetValue(
            str(settings.external_control_osc_port)
        )

        # External Control Midi Port
        external_control_section.Add(
            wx.StaticText(self, label="MIDI port:", style=wx.ALIGN_RIGHT)
        )
        self.external_control_midi_port_control = wx.Choice(self, style=wx.TE_CENTER)
        # Set the Choice's options based off the cached values
        self.update_midi_ports(external_control.get_midi_ports())
        # Trigger a refresh with the callback, which will update the Choice
        external_control.refresh_midi_ports(self.update_midi_ports)
        external_control_section.Add(
            self.external_control_midi_port_control,
            flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL,
        )
        external_control_section.Add(width=label_min_width, height=0)
        self.mmc_control_enabled_checkbox = wx.CheckBox(self, label="MMC enabled")
        self.mmc_control_enabled_checkbox.SetValue(settings.mmc_control_enabled)
        external_control_section.Add(self.mmc_control_enabled_checkbox, flag=wx.EXPAND)
        panel_sizer.Add(
            external_control_section,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=EXTERNAL_SPACING,
        )

        for child in panel_sizer.GetChildren():
            if isinstance(child, wx.SizerItem) and child.IsSizer():
                child_sizer = child.GetSizer()
                if isinstance(child_sizer, wx.FlexGridSizer):
                    child_sizer.SetFlexibleDirection(wx.BOTH)
                    child_sizer.Layout()
                    for flex_child in child_sizer.GetChildren():
                        if (
                            isinstance(flex_child, wx.SizerItem)
                            and not flex_child.IsSpacer()
                        ):
                            flex_child_user_data = flex_child.GetUserData()
                            if flex_child_user_data != LABEL_ROW:
                                flex_child.SetMinSize(wx.Size(label_min_width, -1))
        # Update Button
        update_button = wx.Button(self, -1, "Update")
        panel_sizer.Add(update_button, 0, wx.ALL | wx.EXPAND, EXTERNAL_SPACING)
        self.SetSizer(panel_sizer)
        self.Fit()

        # Update console supported features with the currently set console
        self.update_console_supported_features(console)

        # Prefs Window Bindings
        self.Bind(wx.EVT_BUTTON, self.update_button_pressed, update_button)
        self.console_ip_control.Bind(wx.EVT_TEXT, self.changed_console_ip)
        self.console_ip_control.Bind(wx.EVT_KILL_FOCUS, self.check_console_ip)
        self.console_type_choice.Bind(wx.EVT_CHOICE, self.changed_console_type)
        self.repeater_radio_enabled.Bind(
            wx.EVT_CHECKBOX,
            self.update_repeater_fields,
        )
        self.Show()

    def update_repeater_fields(
        self,
        _event: Optional[wx.CommandEvent] = None,
        console: Optional[Console] = None,
    ) -> None:
        if console is None:
            console = self.console
        else:
            self.console = console
        self.repeater_ip_control.Enabled = (
            Feature.REPEATER in console.supported_features
            and self.repeater_radio_enabled.IsChecked()
        )
        self.repeater_send_port_control.Enabled = (
            Feature.REPEATER in console.supported_features
            and self.repeater_radio_enabled.IsChecked()
        )
        self.repeater_rcv_port_control.Enabled = (
            Feature.REPEATER in console.supported_features
            and self.repeater_radio_enabled.IsChecked()
        )

    def changed_console_type(self, event: wx.CommandEvent) -> None:
        self.console: Console = CONSOLES[event.GetString()]
        self.update_console_supported_features(self.console)

    def update_console_supported_features(self, console: Console) -> None:
        self.match_mode_label_only.Enabled = (
            Feature.CUE_NUMBER in console.supported_features
        )
        self.repeater_radio_enabled.Enabled = (
            Feature.REPEATER in console.supported_features
        )
        self.update_repeater_fields(console=console)
        if Feature.REPEATER not in console.supported_features:
            self.repeater_radio_enabled.SetValue(False)
        if Feature.CUE_NUMBER not in console.supported_features:
            self.match_mode_label_only.SetValue(False)
        if console.fixed_send_port is None:
            self.console_send_port_control.Enable()
        else:
            self.console_send_port_control.SetValue(str(console.fixed_send_port))
            self.console_send_port_control.Disable()
        self.console_rcv_port_control.Enabled = (
            Feature.SEPERATE_RECEIVE_PORT in console.supported_features
        )
        if console.fixed_receive_port is None:
            self.console_rcv_port_control.Enabled = (
                Feature.SEPERATE_RECEIVE_PORT in console.supported_features
            )
        else:
            self.console_rcv_port_control.SetValue(str(console.fixed_receive_port))
            self.console_rcv_port_control.Disable()

    def update_button_pressed(self, e):
        logger.info("Updating configuration settings.")
        # Writing the new values from the preferences panel to settings
        try:
            settings.console_ip = self.console_ip_control.GetValue()
            settings.console_port = str(self.console_send_port_control.GetValue())
            settings.receive_port = str(self.console_rcv_port_control.GetValue())
            settings.repeater_ip = self.repeater_ip_control.GetValue()
            settings.repeater_port = str(self.repeater_send_port_control.GetValue())
            settings.repeater_receive_port = str(
                self.repeater_rcv_port_control.GetValue()
            )
            settings.name_only_match = self.match_mode_label_only.GetValue()
            settings.forwarder_enabled = self.repeater_radio_enabled.GetValue()
            settings.console_type = self.console_type_choice.GetString(
                self.console_type_choice.GetSelection()
            )
            settings.daw_type = self.daw_type_choice.GetString(
                self.daw_type_choice.GetSelection()
            )
            settings.always_on_top = self.always_on_top_checkbox.GetValue()
            settings.external_control_osc_port = int(
                self.external_control_osc_port_control.GetValue()
            )
            settings.external_control_midi_port = (
                self.external_control_midi_port_control.GetString(
                    self.external_control_midi_port_control.GetSelection()
                )
            )
            settings.mmc_control_enabled = self.mmc_control_enabled_checkbox.GetValue()
            # Force a close/reconnect of the OSC servers by pushing the configuration update.
            MainWindow.BridgeFunctions.update_configuration_file(
                con_ip=settings.console_ip,
                rptr_ip=settings.repeater_ip,
                con_send=settings.console_port,
                con_rcv=settings.receive_port,
                fwd_enable=settings.forwarder_enabled,
                rpr_send=settings.reaper_port,
                rpr_rcv=settings.reaper_receive_port,
                rptr_snd=settings.repeater_port,
                rptr_rcv=settings.repeater_receive_port,
                name_only=settings.name_only_match,
                console_type=settings.console_type,
                daw_type=settings.daw_type,
                always_on_top=settings.always_on_top,
                external_control_osc_port=settings.external_control_osc_port,
                external_control_midi_port=settings.external_control_midi_port,
                mmc_control_enabled=settings.mmc_control_enabled,
            )
            MainWindow.BridgeFunctions.shutdown_and_restart_servers()
            # Close the preferences window when update is pressed.
            self.Parent.Destroy()
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
        pub.sendMessage(PyPubSubTopics.UPDATE_MAIN_WINDOW_DISPLAY_SETTINGS)

    def changed_console_ip(self, e):
        # Flag to know if the console IP has been modified in the prefs window
        self.ip_inspected = False

    def check_console_ip(self, e):
        # Validates input into the console IP address field
        # Use the ip_address function from the ipaddress module to check if the input is a valid IP address
        ip = self.console_ip_control.GetValue()

        if not self.ip_inspected:
            self.ip_inspected = True
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                logger.warning(f"Invalid IP address entered: {ip}")
                # If the input is not a valid IP address, catch the exception and show a dialog
                dlg = wx.MessageDialog(
                    self,
                    "This is not a valid IP address for the console. Please try again",
                    constants.APPLICATION_NAME,
                    wx.OK,
                )
                dlg.ShowModal()  # Shows it
                dlg.Destroy()  # Destroy pop-up when finished.
                # Put the focus back on the bad field
                wx.CallAfter(self.console_ip_control.SetFocus)

    def update_midi_ports(self, ports: list[str]) -> None:
        def update(self: PrefsPanel, ports: list[str]) -> None:
            self.external_control_midi_port_control.Set(ports)
            if settings.external_control_midi_port in ports:
                self.external_control_midi_port_control.SetSelection(
                    ports.index(settings.external_control_midi_port)
                )

        if wx.IsMainThread():  # pyright: ignore[reportCallIssue]
            update(self, ports)
        else:
            wx.CallAfter(update, self, ports)


if __name__ == "__main__":
    try:
        logger.info(f"Starting {constants.APPLICATION_NAME} Application")
        app = wx.App(False)
        app.SetAppName(constants.APPLICATION_NAME)
        app.SetAppDisplayName(constants.APPLICATION_NAME)
        frame = MainWindow()
        app.SetTopWindow(frame)
        external_control.refresh_midi_ports()
        app.MainLoop()
    except Exception as e:
        logger.critical(f"Fatal Error: {e}", exc_info=True)
