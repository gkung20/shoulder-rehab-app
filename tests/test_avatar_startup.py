"""Check native-library initialization independently of a webcam or GPU window."""
import subprocess
import sys
import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native-library initialization order")
def test_voice_runtime_preloads_before_panda_in_fresh_process():
    script="""
import sys
from src.avatar_stage import prepare_native_runtime
assert 'panda3d.core' not in sys.modules
prepare_native_runtime()
assert 'onnxruntime' in sys.modules
import panda3d.core
from piper import PiperVoice
import onnxruntime
assert onnxruntime.get_available_providers()
print('native-startup-ok')
"""
    result=subprocess.run([sys.executable,"-X","faulthandler","-c",script],
                          capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout+result.stderr
    assert "native-startup-ok" in result.stdout
