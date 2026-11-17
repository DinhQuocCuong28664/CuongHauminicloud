# -*- coding: utf-8 -*-
"""chrome_raise.py - bring the demo Chrome WINDOW (not only the tab) in front of other windows.

page.bring_to_front() only activates the tab inside its window; when another window (a second Chrome with a
video call, an editor, ...) has the focus, the demo window stays behind and the demo looks like "nothing opened".
The demo Chrome is found by its browser process id (asked over the DevTools protocol), because the user's own
Chrome windows share the same window class and often the same kind of title. Windows refuses plain
SetForegroundWindow calls from a background process, so a synthetic Alt key press and AttachThreadInput are used.
"""
import ctypes
import sys
import time


def _browser_pid(page):
    session = page.context.browser.new_browser_cdp_session()
    try:
        info = session.send("SystemInfo.getProcessInfo")["processInfo"]
        return next(p["id"] for p in info if p["type"] == "browser")
    finally:
        session.detach()


def _find_window(pid):
    """Largest visible top-level Chrome window owned by the process."""
    user32 = ctypes.windll.user32
    found = []
    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            owner = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if owner.value == pid and cls.value == "Chrome_WidgetWin_1":
                rect = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append(((rect.r - rect.l) * (rect.b - rect.t), hwnd))
        return True

    user32.EnumWindows(enum_proc(cb), 0)
    return max(found)[1] if found else None


def _force_foreground(hwnd):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    tid_fg = user32.GetWindowThreadProcessId(fg, None)
    tid_me = kernel32.GetCurrentThreadId()
    user32.keybd_event(0x12, 0, 0, 0)          # Alt down: lets this process take the foreground
    user32.keybd_event(0x12, 0, 2, 0)          # Alt up
    user32.AttachThreadInput(tid_me, tid_fg, True)
    user32.ShowWindow(hwnd, 9)                 # SW_RESTORE (if minimized)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(tid_me, tid_fg, False)


def raise_window(page):
    if sys.platform != "win32":
        return
    try:
        page.bring_to_front()
        hwnd = _find_window(_browser_pid(page))
        if hwnd:
            time.sleep(0.1)
            _force_foreground(hwnd)
    except Exception:
        pass   # best effort: the tab is still active even if the window cannot be raised
