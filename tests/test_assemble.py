from unittest.mock import MagicMock, patch

import pytest

from capt.assemble import _check_ffmpeg_available


def test_check_ffmpeg_available_passes_when_both_binaries_work():
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        _check_ffmpeg_available()  # should not raise


def test_check_ffmpeg_available_raises_clearly_when_binary_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError("no ffmpeg")):
        with pytest.raises(RuntimeError, match="isn't installed"):
            _check_ffmpeg_available()


def test_check_ffmpeg_available_raises_clearly_when_binary_broken():
    broken = MagicMock(returncode=1, stdout="", stderr="dyld: Library not loaded: libSvtAv1Enc.3.dylib")
    with patch("subprocess.run", return_value=broken):
        with pytest.raises(RuntimeError, match="failed to run"):
            _check_ffmpeg_available()
