"""Faster drawing (Phase 6.3) changes no pixel: cached and fresh renders are identical."""
import itertools
import time

import numpy as np
import pytest

from src.config import ExerciseConfig
from src.dashboard import render_dashboard
from src.session_processor import SessionProcessor
from src.synthetic_pose import body
from src.willy import RENDER_CACHE_BYTES, WillyGuide, WillyPose


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(time, "monotonic", lambda: 1000.)


def test_cached_and_fresh_dashboards_are_identical(frozen):
    processor = SessionProcessor(ExerciseConfig.from_yaml())
    analysis = None
    for i in range(10):
        pts, world = body(0)
        analysis = processor.process(pts, world, 640, 480, i / 30)
    camera = np.random.default_rng(2).integers(20, 220, (480, 640, 3), dtype=np.uint8)
    guide = WillyGuide()
    states = itertools.product(("ready", "running", "paused", "finished"), (False, True), (False, True), ("fr", "en"))
    for mode, help_visible, silhouette, lang in states:
        kwargs = dict(mode=mode, help_visible=help_visible, silhouette=silhouette, lang=lang, avatars=False,
                      willy=guide, output_size=(1600, 1000))
        cached = render_dashboard(camera, analysis, processor, **kwargs)
        again = render_dashboard(camera, analysis, processor, **kwargs)  # from the cache this time
        fresh = render_dashboard(camera, analysis, processor, cache=False, **kwargs)
        assert np.array_equal(cached, fresh) and np.array_equal(again, fresh), (mode, help_visible, silhouette, lang)


def test_willy_reuses_recent_renders_within_a_memory_bound():
    guide = WillyGuide()
    first = None
    for mouth in ("smile", "talk1", "talk2", "smile"):
        guide.pose = WillyPose(mouth=mouth)
        image = guide.render(208, 276)
        first = first if first is not None else image
    assert image is first  # the same pose comes back from the cache
    for size in range(200, 900, 20):  # many big renders: the cache stays bounded
        guide.render(size, size * 4 // 3)
    assert guide._render_bytes <= RENDER_CACHE_BYTES + 900 * 1200 * 4
