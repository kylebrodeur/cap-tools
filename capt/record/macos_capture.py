"""Global click/keystroke capture for macOS — an alternative marker source
to scripted Playwright steps, so a manual walkthrough (no steps.json) still
produces automatic zoom segments.

Requires the "Input Monitoring" permission (System Settings > Privacy &
Security > Input Monitoring) for whatever terminal/app this runs from. This
is a DIFFERENT permission from "Accessibility" — Accessibility is what
Phase 2/3's AXUIElement-based window inspection and native-app automation
will need later, not this module.
"""

import threading
from typing import Optional

import Quartz

HOTKEY_FLAGS = Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift
HOTKEY_KEYCODE = 46  # 'm' on a standard US keyboard layout


def is_hotkey_event(event_type: int, flags: int, keycode: int) -> bool:
    """Pure matcher: does this raw key-down event match the mark hotkey
    (Cmd+Shift+M)? Kept separate from the CGEventTap wiring so it's testable
    without a live tap or granted permission. Extra flags (e.g. Caps Lock)
    are tolerated as long as Cmd+Shift are both present.
    """
    return (
        event_type == Quartz.kCGEventKeyDown
        and (flags & HOTKEY_FLAGS) == HOTKEY_FLAGS
        and keycode == HOTKEY_KEYCODE
    )


class GlobalCapture:
    """Installs a CGEventTap for the lifetime of start()/stop(), marking
    `tracker` on every left/right mouse click and on the mark hotkey."""

    def __init__(self, tracker, label_prefix: str = "click"):
        self.tracker = tracker
        self.label_prefix = label_prefix
        self._tap = None
        self._run_loop = None
        self._run_loop_source = None
        self._thread: Optional[threading.Thread] = None

    def _callback(self, proxy, event_type, event, refcon):
        if event_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown):
            self.tracker.mark(self.label_prefix)
        elif event_type == Quartz.kCGEventKeyDown:
            flags = Quartz.CGEventGetFlags(event)
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if is_hotkey_event(event_type, flags, keycode):
                self.tracker.mark("manual-mark")
        return event

    def start(self) -> None:
        if self._tap is not None:
            raise RuntimeError("GlobalCapture is already started — call stop() first")

        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            raise PermissionError(
                "Could not create a global event tap — grant Input Monitoring "
                "to this terminal/app in System Settings > Privacy & Security "
                "> Input Monitoring, then restart the terminal and try again."
            )

        ready = threading.Event()

        def _run():
            self._run_loop = Quartz.CFRunLoopGetCurrent()
            self._run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            Quartz.CFRunLoopAddSource(self._run_loop, self._run_loop_source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(self._tap, True)
            ready.set()
            Quartz.CFRunLoopRun()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        ready.wait(timeout=2)

    def stop(self) -> None:
        if self._run_loop is not None:
            Quartz.CFRunLoopStop(self._run_loop)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._tap = None
        self._run_loop = None
        self._run_loop_source = None
        self._thread = None
