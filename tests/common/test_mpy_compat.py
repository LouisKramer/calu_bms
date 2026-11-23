"""T12: the shared firmware modules compile with mpy-cross (MicroPython syntax subset)."""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

FIRMWARE = pathlib.Path(__file__).resolve().parents[2] / "firmware"


@pytest.mark.skipif(importlib.util.find_spec("mpy_cross") is None, reason="mpy-cross not installed")
@pytest.mark.parametrize("src", sorted((FIRMWARE / "common").glob("*.py")), ids=lambda s: s.name)
def test_compiles_for_micropython(src, tmp_path):
    out = tmp_path / (src.stem + ".mpy")
    result = subprocess.run([sys.executable, "-m", "mpy_cross", "-o", str(out), str(src)], capture_output=True,
                            stdin=subprocess.DEVNULL, text=True)
    assert result.returncode == 0, result.stderr
