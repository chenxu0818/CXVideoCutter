"""Windows 任务栏图标进度，不引入额外依赖。

通过 COM 的 ITaskbarList3 调用 SetProgressValue / SetProgressState。
非 Windows 或调用失败时自动降级为空操作，调用方无需判断平台。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import (
    POINTER, Structure, byref, c_int, c_ubyte, c_ulong, c_ulonglong,
    c_ushort, c_void_p, cast,
)

try:
    from ctypes import WINFUNCTYPE
except ImportError:  # 非 Windows
    WINFUNCTYPE = None  # type: ignore[assignment]


class GUID(Structure):
    _fields_ = [
        ("data1", c_ulong),
        ("data2", c_ushort),
        ("data3", c_ushort),
        ("data4", c_ubyte * 8),
    ]


CLSID_TaskbarList = GUID(
    0x56CD7819, 0xCDDC, 0x4216,
    (c_ubyte * 8)(0x84, 0x29, 0x29, 0x66, 0xA9, 0xDD, 0x3F, 0x75),
)
IID_ITaskbarList3 = GUID(
    0xEA1B63D1, 0x3B65, 0x43CF,
    (c_ubyte * 8)(0xBC, 0x2B, 0xD4, 0x7E, 0x4B, 0x9C, 0x3D, 0x8E),
)


class TaskbarProgress:
    TBPF_NOPROGRESS = 0
    TBPF_INDETERMINATE = 1
    TBPF_NORMAL = 2
    TBPF_ERROR = 4
    TBPF_PAUSED = 8

    def __init__(self, hwnd: int = 0):
        self.hwnd = int(hwnd or 0)
        self._tb: c_void_p | None = None
        self._set_value = None
        self._set_state = None
        self._hr_init = None
        if sys.platform != "win32" or WINFUNCTYPE is None:
            return
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return
        try:
            ole32 = windll.ole32
            hresult = getattr(ctypes, "HRESULT", c_int)
            ole32.CoInitializeEx.argtypes = [c_void_p, c_ulong]
            ole32.CoInitializeEx.restype = hresult
            ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED，已初始化时忽略返回值
            ole32.CoCreateInstance.argtypes = [
                POINTER(GUID), c_void_p, c_ulong, POINTER(GUID), POINTER(c_void_p)
            ]
            ole32.CoCreateInstance.restype = hresult
            ptr = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(CLSID_TaskbarList), None, 1, byref(IID_ITaskbarList3), byref(ptr)
            )
            if hr < 0 or not ptr.value:
                return
            table = cast(ptr.value, POINTER(c_void_p))
            self._tb = ptr
            self._hr_init = WINFUNCTYPE(hresult, c_void_p)(table[3])
            self._set_value = WINFUNCTYPE(
                hresult, c_void_p, c_void_p, c_ulonglong, c_ulonglong
            )(table[9])
            self._set_state = WINFUNCTYPE(hresult, c_void_p, c_void_p, c_int)(table[10])
            self._hr_init(self._tb)
        except Exception:
            self._tb = None
            self._set_value = None
            self._set_state = None

    def set_hwnd(self, hwnd: int) -> None:
        self.hwnd = int(hwnd or 0)

    def set_state(self, state: int) -> None:
        if self._tb is None or not self.hwnd or self._set_state is None:
            return
        try:
            self._set_state(self._tb, c_void_p(self.hwnd), int(state))
        except Exception:
            pass

    def set_value(self, value: int) -> None:
        if self._tb is None or not self.hwnd or self._set_value is None:
            return
        value = max(0, min(100, int(value)))
        try:
            self._set_value(self._tb, c_void_p(self.hwnd), value, 100)
        except Exception:
            pass

    def reset(self) -> None:
        self.set_state(self.TBPF_NOPROGRESS)
        self.set_value(0)
