"""Fullscreen must preserve proportions and align mouse targets with visible buttons."""
import cv2
import numpy as np
import pytest

from src.patient_controls import patient_buttons, dashboard_action_at
from src.window_viewport import fit_window, fit_native_window


@pytest.mark.parametrize("width,height",[(1920,1080),(2560,1080),(900,1200),(800,600),(1280,840)])
def test_resizing_keeps_a_circle_round_and_the_entire_canvas_visible(width,height):
    source=np.zeros((840,1280,3),np.uint8)
    cv2.circle(source,(640,420),100,(0,255,0),-1)
    for x,y in ((5,5),(1274,5),(5,834),(1274,834)):
        cv2.rectangle(source,(x-3,y-3),(x+3,y+3),(255,0,0),-1)
    image,viewport=fit_window(source,width,height)
    assert image.shape == (height,width,3)
    assert viewport.left >= 0 and viewport.top >= 0
    assert viewport.left+viewport.content_width <= width
    assert viewport.top+viewport.content_height <= height
    yy,xx=np.where((image[:,:,1]>200) & (image[:,:,0]<30))
    assert abs(np.ptp(xx)-np.ptp(yy)) <= 2  # The old stretch turns this circle into an ellipse.
    # All four corner markers survive: fitting must not crop to fill the viewport.
    for x,y in ((5,5),(1274,5),(5,834),(1274,834)):
        px=viewport.left+round(x*viewport.content_width/1280)
        py=viewport.top+round(y*viewport.content_height/840)
        assert image[py,px,0]>100


@pytest.mark.parametrize("width,height",[(1920,1080),(2560,1080),(900,1200),(800,600)])
def test_resized_buttons_remain_clickable_and_margins_do_nothing(width,height):
    _,viewport=fit_window(np.zeros((840,1280,3),np.uint8),width,height)
    for button in patient_buttons(mode="ready"):
        x1,y1,x2,y2=button.bounds
        px=viewport.left+(x1+x2)/2*viewport.content_width/1280
        py=viewport.top+(y1+y2)/2*viewport.content_height/840
        point=viewport.canvas_point(px,py)
        assert dashboard_action_at(*point,mode="ready") == (button.action if button.enabled else None)
    if viewport.left:
        assert viewport.canvas_point(viewport.left-1,height/2) is None
    if viewport.top:
        assert viewport.canvas_point(width/2,viewport.top-1) is None


def test_minimized_or_unavailable_window_has_safe_initial_mapping(monkeypatch):
    source=np.zeros((840,1280,3),np.uint8)
    monkeypatch.setattr(cv2,"getWindowImageRect",lambda name: (0,0,0,0))
    image,viewport=fit_native_window("test",source)
    assert image is source
    assert viewport.canvas_point(100,760) == (100,760)
    def unsupported(name):
        raise cv2.error("Window not ready")
    monkeypatch.setattr(cv2,"getWindowImageRect",unsupported)
    image,viewport=fit_native_window("test",source)
    assert image is source
    assert viewport.canvas_point(100,760) == (100,760)


def test_high_dpi_awareness_is_requested_before_native_window_creation(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from unittest.mock import Mock
    import src.window_viewport as module
    request=Mock(return_value=True)
    monkeypatch.setattr(module,"sys",SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes,"windll",SimpleNamespace(user32=SimpleNamespace(SetProcessDpiAwarenessContext=request)),raising=False)
    module.enable_high_dpi()
    request.assert_called_once()
    assert request.call_args.args[0].value == ctypes.c_void_p(-4).value
