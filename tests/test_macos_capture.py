from unittest.mock import MagicMock

import pytest

pytest.importorskip("Quartz")

from capt.record.macos_capture import GlobalCapture, is_hotkey_event, HOTKEY_FLAGS, HOTKEY_KEYCODE
import Quartz


def test_is_hotkey_event_matches_cmd_shift_m():
    assert is_hotkey_event(Quartz.kCGEventKeyDown, HOTKEY_FLAGS, HOTKEY_KEYCODE) is True


def test_is_hotkey_event_rejects_wrong_keycode():
    assert is_hotkey_event(Quartz.kCGEventKeyDown, HOTKEY_FLAGS, 99) is False


def test_is_hotkey_event_rejects_missing_modifier():
    assert is_hotkey_event(Quartz.kCGEventKeyDown, Quartz.kCGEventFlagMaskShift, HOTKEY_KEYCODE) is False


def test_is_hotkey_event_rejects_non_keydown_type():
    assert is_hotkey_event(Quartz.kCGEventKeyUp, HOTKEY_FLAGS, HOTKEY_KEYCODE) is False


def test_is_hotkey_event_ignores_extra_flags():
    # Caps lock or other incidental flags shouldn't break the match, as long
    # as Cmd+Shift are both present.
    extra = HOTKEY_FLAGS | Quartz.kCGEventFlagMaskAlphaShift
    assert is_hotkey_event(Quartz.kCGEventKeyDown, extra, HOTKEY_KEYCODE) is True


def test_global_capture_start_and_stop_run_cleanly_when_permission_granted():
    # Input Monitoring is granted on this machine (verified during Task 3's
    # implementation) — this exercises the granted-permission path for real,
    # replacing the permission-denied test per the plan's documented fallback
    # (see the note after Task 3's Step 6 in the plan).
    tracker = MagicMock()
    capture = GlobalCapture(tracker)
    capture.start()
    capture.stop()


def test_global_capture_start_twice_raises_without_stop():
    # Calling start() again before stop() would otherwise leak the first
    # tap/thread (orphaned, never torn down) since stop() only tears down
    # whatever's currently referenced. Guard against that.
    tracker = MagicMock()
    capture = GlobalCapture(tracker)
    capture.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            capture.start()
    finally:
        capture.stop()
