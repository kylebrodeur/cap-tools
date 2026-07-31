"""macOS-only preflight gate: is the Input Monitoring permission granted for
global-capture marker collection?

Reuses GlobalCapture itself (start/stop) rather than a separate permission
query API, since CGEventTapCreate returning None IS the permission-denied
signal — no second API to get wrong.
"""

from capt.record.macos_capture import GlobalCapture


def gate_global_capture_permission() -> tuple[bool, str]:
    capture = GlobalCapture(tracker=None)
    try:
        capture.start()
    except PermissionError as e:
        return False, str(e)
    else:
        capture.stop()
        return True, "Input Monitoring granted (global-capture available)"
