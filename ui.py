import os
from typing import Optional

import wx.lib.buttons
import wx.svg

import constants
import utilities

if not (constants.WXPYTHON_USE_NATIVE_BUTTONS or os.getenv("UGLY_MODE")):

    class NoBorderBitmapButton(wx.lib.buttons.GenBitmapButton):
        icon: str
        playback_state: Optional[constants.PlaybackState]
        icon_svg_on: wx.svg.SVGimage
        icon_svg_off: wx.svg.SVGimage

        def __init__(
            self,
            parent,
            playback_state: Optional[constants.PlaybackState] = None,
            icon: str = str(),
            id=wx.ID_ANY,
            pos=wx.DefaultPosition,
            size=wx.Size(52, 52),
            style=0,
            validator=wx.DefaultValidator,
            name="noborderbitmaptoggle",
        ):
            super().__init__(
                parent, id, wx.NullBitmap, pos, size, style, validator, name
            )
            self.icon = icon
            self.playback_state = playback_state
            if playback_state is not None:
                self.icon = playback_state
            self.icon_svg_on = get_icon_svg(self.icon, "on")
            self.icon_svg_off = get_icon_svg(self.icon, "off")

        def SetBitmapLabel(self, bitmap, createOthers=True):
            pass

        def _GetLabelSize(self):
            return 52, 52, True

        def OnPaint(self, event):
            (width, height) = self.GetClientSize()
            dc = wx.PaintDC(self)
            if wx.Platform == "__WXMSW__":
                brush = self.GetBackgroundBrush(dc)
                if brush is not None:
                    dc.SetBackground(brush)
                    dc.Clear()
            self.DrawLabel(dc, width, height)

        def GetBackgroundBrush(self, dc):
            colBg = self.GetBackgroundColour()
            brush = wx.Brush(colBg)
            if self.style & wx.BORDER_NONE:
                myAttr = self.GetDefaultAttributes()
                parAttr = self.GetParent().GetDefaultAttributes()
                myDef = colBg == myAttr.colBg
                parDef = self.GetParent().GetBackgroundColour() == parAttr.colBg
                if myDef and parDef:
                    if hasattr(self, "DoEraseBackground") and self.DoEraseBackground(
                        dc
                    ):  # pyright: ignore[reportAttributeAccessIssue]
                        brush = None
                elif myDef and not parDef:
                    colBg = self.GetParent().GetBackgroundColour()
                    brush = wx.Brush(colBg)
            return brush

        def DrawLabel(self, dc: wx.DC, width, height, dx=0, dy=0):
            gc = wx.GraphicsContext.Create(dc)
            if self.up:
                self.icon_svg_off.RenderToGC(gc, 0.5)
            else:
                self.icon_svg_on.RenderToGC(gc, 0.5)

        def Notify(self):
            evt = MarkerMaticButtonEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, self.GetId())
            evt.SetIsDown(not self.up)
            evt.IsChecked()
            evt.SetButtonObj(self)
            evt.SetEventObject(self)
            self.GetEventHandler().ProcessEvent(evt)

    class NoBorderBitmapToggle(wx.lib.buttons.__ToggleMixin, NoBorderBitmapButton):
        playback_state: constants.PlaybackState

        def __init__(
            self,
            parent,
            playback_state: constants.PlaybackState,
            icon: str = str(),
            id=wx.ID_ANY,
            pos=wx.DefaultPosition,
            size=wx.Size(52, 52),
            style=0,
            validator=wx.DefaultValidator,
            name="noborderbitmaptoggle",
        ):
            super().__init__(
                parent, playback_state, icon, id, pos, size, style, validator, name
            )

    class MarkerMaticButtonEvent(wx.lib.buttons.GenButtonEvent):
        def IsChecked(self) -> bool:
            return self.isDown
else:

    class NoBorderBitmapButton(wx.BitmapButton):
        playback_state: Optional[constants.PlaybackState]

        def __init__(
            self,
            parent,
            playback_state: Optional[constants.PlaybackState] = None,
            icon: str = str(),
            id=wx.ID_ANY,
            pos=wx.DefaultPosition,
            size=wx.Size(52, 52),
            style=0,
            validator=wx.DefaultValidator,
            name="noborderbitmaptoggle",
        ):
            self.icon = icon
            self.playback_state = playback_state
            if playback_state is not None:
                self.icon = playback_state
            super().__init__(
                parent, id, wx.BitmapBundle.FromSVGFile(get_icon_path(self.icon), size)
            )
            bitmap_bundle_on = wx.BitmapBundle.FromSVGFile(
                get_icon_path(self.icon, "on"), size
            )
            self.SetBitmapPressed(bitmap_bundle_on)
            self.SetBitmapDisabled(bitmap_bundle_on)

    class NoBorderBitmapToggle(wx.BitmapToggleButton):
        playback_state: constants.PlaybackState

        def __init__(
            self,
            parent,
            playback_state: constants.PlaybackState,
            icon: str = str(),
            id=wx.ID_ANY,
            pos=wx.DefaultPosition,
            size=wx.Size(52, 52),
            style=0,
            validator=wx.DefaultValidator,
            name="noborderbitmaptoggle",
        ):
            self.icon = icon
            self.playback_state = playback_state
            if playback_state is not None:
                self.icon = playback_state
            super().__init__(
                parent,
                id,
                wx.BitmapBundle.FromSVGFile(get_icon_path(self.icon), size),
            )
            bitmap_bundle_on = wx.BitmapBundle.FromSVGFile(
                get_icon_path(self.icon, "on"), size
            )
            self.SetBitmapPressed(bitmap_bundle_on)
            self.SetBitmapDisabled(bitmap_bundle_on)

        def SetValue(self, state: bool) -> None:
            self.Enabled = not state
            super().SetValue(state)


class ToggleableStaticBitmap(wx.StaticBitmap):
    _bitmapbundle_on: wx.BitmapBundle
    _bitmapbundle_off: wx.BitmapBundle
    state: bool

    def __init__(
        self,
        parent: wx.Window,
        icon_name: str,
        state: bool = False,
        id: int = wx.ID_ANY,
        pos: wx.Point = wx.DefaultPosition,
        size: wx.Size = wx.DefaultSize,
        style: int = 0,
        name: str = wx.StaticBitmapNameStr,
    ) -> None:
        self._bitmapbundle_off = wx.BitmapBundle.FromSVGFile(
            get_icon_path(icon_name, "off"), size
        )
        self._bitmapbundle_on = wx.BitmapBundle.FromSVGFile(
            get_icon_path(icon_name, "on"), size
        )

        self.state = state

        super().__init__(
            parent,
            id=id,
            bitmap=self._get_bitmapbundle(self.state),
            pos=pos,
            size=size,
            style=style,
            name=name,
        )

    def _get_bitmapbundle(self, state: bool) -> wx.BitmapBundle:
        if state:
            return self._bitmapbundle_on
        return self._bitmapbundle_off

    def set_state(self, state: bool) -> None:
        self.state = state
        self.SetBitmap(self._get_bitmapbundle(state))


def get_icon_svg(icon_name: str, state: str = "off") -> wx.svg.SVGimage:
    return wx.svg.SVGimage.CreateFromFile(get_icon_path(icon_name, state))


def get_icon_path(icon_name: str, state: str = "off") -> str:
    if wx.Platform == "__WXMSW__":
        path = os.path.abspath(
            os.path.join(
                utilities.get_resources_directory_path(),
                "icons",
                f"{icon_name}-{state}-solid.svg",
            )
        )
        if os.path.exists(path):
            return path
    return os.path.abspath(
        os.path.join(
            utilities.get_resources_directory_path(),
            "icons",
            f"{icon_name}-{state}.svg",
        )
    )
