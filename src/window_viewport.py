"""Preserve dashboard proportions independently of HighGUI's native stretching.

HighGUI mouse callbacks are expressed in the submitted image's coordinates.
Submit a window-sized, letterboxed image and undo that letterboxing for buttons.
"""
from dataclasses import dataclass
import cv2
import numpy as np
import sys


@dataclass(frozen=True)
class WindowViewport:
    source_width: int
    source_height: int
    left: int
    top: int
    content_width: int
    content_height: int

    def canvas_point(self, x, y):
        if not (self.left <= x < self.left+self.content_width
                and self.top <= y < self.top+self.content_height):
            return None
        return ((x-self.left)*self.source_width/self.content_width,
                (y-self.top)*self.source_height/self.content_height)


def canvas_viewport(source_size, width, height):
    """Layout transform shared by native-resolution drawing and mouse mapping."""
    source_width,source_height=source_size
    if width <= 0 or height <= 0:
        width,height=source_width,source_height
    scale=min(width/source_width,height/source_height)
    content_width=min(width,max(1,round(source_width*scale)))
    content_height=min(height,max(1,round(source_height*scale)))
    left,top=(width-content_width)//2,(height-content_height)//2
    return WindowViewport(source_width,source_height,left,top,content_width,content_height)


def native_window_size(name, fallback=(1280,840)):
    try:
        _,_,width,height=cv2.getWindowImageRect(name)
        if width > 0 and height > 0:
            return width,height
    except cv2.error:
        pass
    return fallback


def enable_high_dpi():
    """Ask Windows for physical pixels before creating a window, avoiding OS bitmap scaling."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return  # Per-monitor V2, Windows 10 and later.
    except (AttributeError,OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError,OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError,OSError):
            pass


def fit_window(image, width, height, background=(249,250,250)):
    """Compatibility fitting for bitmap previews, not the native UI text-rendering path."""
    source_height,source_width=image.shape[:2]
    if width <= 0 or height <= 0:
        width,height=source_width,source_height
    viewport=canvas_viewport((source_width,source_height),width,height)
    left,top=viewport.left,viewport.top
    content_width,content_height=viewport.content_width,viewport.content_height
    if (width,height) == (source_width,source_height):
        return image,viewport
    canvas=np.full((height,width,3),background,dtype=image.dtype)
    resized=cv2.resize(image,(content_width,content_height),
                       interpolation=cv2.INTER_AREA if content_width < source_width else cv2.INTER_LINEAR)
    canvas[top:top+content_height,left:left+content_width]=resized
    return canvas,viewport


def fit_native_window(name, image):
    return fit_window(image,*native_window_size(name,(image.shape[1],image.shape[0])))
