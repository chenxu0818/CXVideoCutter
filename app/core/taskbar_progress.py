"""Windows 任务栏图标进度，不引入额外依赖。

通过 COM 的 ITaskbarList3 调用 SetProgressValue / SetProgressState。

关键设计：
1. 延迟初始化：必须拿到顶层窗口 HWND 后才创建 COM 对象，且可重试。
2. 多路径创建：CoCreateInstance(CLSCTX_ALL) → explorerframe.dll → shell32.dll。
3. 全链路诊断：每一步的 HRESULT、HWND、调用返回值都写入日志，便于定位。
4. 非 Windows 或任何失败都自动降级为空操作，调用方无需判断平台。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import (
    POINTER, Structure, byref, c_int, c_ubyte, c_ulong, c_ulonglong,
    c_ushort, c_void_p, cast,
)

from .logger import log_info, log_warn

try:
    from ctypes import WINFUNCTYPE
except ImportError:  # 非 Windows
    WINFUNCTYPE = None  # type: ignore[assignment]


def _hr_text(hr: int) -> str:
    return f"0x{hr & 0xFFFFFFFF:08X}"


CLSCTX_ALL = 0x17          # INPROC | INPROC_HANDLER | LOCAL | REMOTE
COINIT_APARTMENTTHREADED = 0x2


class GUID(Structure):
    _fields_ = [
        ("data1", c_ulong),
        ("data2", c_ushort),
        ("data3", c_ushort),
        ("data4", c_ubyte * 8),
    ]


# 注意：以下 GUID 必须精确匹配 Windows SDK 定义，写错会导致 CoCreateInstance
# 返回 REGDB_E_CLASSNOTREG (0x80040154) —— 表现为任务栏进度完全不显示。
# CLSID_TaskbarList   = 56FDF344-FD6D-11D0-958A-006097C9A090
# IID_ITaskbarList3   = EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF
# IID_IClassFactory   = 00000001-0000-0000-C000-000000000046
CLSID_TaskbarList = GUID(
    0x56FDF344, 0xFD6D, 0x11D0,
    (c_ubyte * 8)(0x95, 0x8A, 0x00, 0x60, 0x97, 0xC9, 0xA0, 0x90),
)
IID_ITaskbarList3 = GUID(
    0xEA1AFB91, 0x9E28, 0x4B86,
    (c_ubyte * 8)(0x90, 0xE9, 0x9E, 0x9F, 0x8A, 0x5E, 0xEF, 0xAF),
)
IID_IClassFactory = GUID(
    0x00000001, 0x0000, 0x0000,
    (c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46),
)


class TaskbarProgress:
    TBPF_NOPROGRESS = 0
    TBPF_INDETERMINATE = 1
    TBPF_NORMAL = 2
    TBPF_ERROR = 4
    TBPF_PAUSED = 8

    def __init__(self, hwnd: int = 0):
        self.hwnd = 0
        self._tb: c_void_p | None = None
        self._add_tab = None
        self._set_value = None
        self._set_state = None
        self._hr_init = None
        self._ready = False
        self._path = ""
        self._retries = 0
        self._max_retries = 5
        if hwnd:
            self.set_hwnd(hwnd)

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def set_hwnd(self, hwnd: int) -> None:
        hwnd = int(hwnd or 0)
        if not hwnd:
            return
        hwnd_changed = hwnd != self.hwnd
        self.hwnd = hwnd
        # 已就绪且窗口未变：无需重复创建 COM 对象
        if self._ready and not hwnd_changed:
            return
        # 每次拿到（新的）HWND 都允许重建，避免构造期失败后永久失效
        self._ready = False
        self._tb = None
        self._init_now()

    def _init_now(self) -> None:
        if sys.platform != "win32" or WINFUNCTYPE is None:
            log_warn("任务栏进度：非 Windows 平台，跳过")
            return
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            log_warn("任务栏进度：ctypes.windll 不可用，跳过")
            return
        try:
            ole32 = windll.ole32
            ole32.CoInitializeEx.argtypes = [c_void_p, c_ulong]
            ole32.CoInitializeEx.restype = c_int
            # Qt 可能已初始化 COM：S_FALSE / RPC_E_CHANGED_MODE 均可忽略
            hr_co = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
            log_info(f"任务栏进度：CoInitializeEx hr={_hr_text(hr_co)}")

            ole32.CoCreateInstance.argtypes = [
                POINTER(GUID), c_void_p, c_ulong, POINTER(GUID), POINTER(c_void_p)
            ]
            ole32.CoCreateInstance.restype = c_int

            ptr = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(CLSID_TaskbarList), None, CLSCTX_ALL,
                byref(IID_ITaskbarList3), byref(ptr),
            )
            path = f"CoCreateInstance(CLSCTX_ALL) hr={_hr_text(hr)}"
            log_info(f"任务栏进度：路径1 {path}")

            # 路径2/3：注册表被过滤或类未注册时，直接从系统 DLL 取类工厂
            if hr < 0 or not ptr.value:
                hr, ptr = self._create_via_dll(windll, "explorerframe.dll")
                path = f"explorerframe.dll hr={_hr_text(hr)}"
                log_info(f"任务栏进度：路径2 {path}")
            if hr < 0 or not ptr.value:
                hr, ptr = self._create_via_dll(windll, "shell32.dll")
                path = f"shell32.dll hr={_hr_text(hr)}"
                log_info(f"任务栏进度：路径3 {path}")

            if hr < 0 or not ptr.value:
                log_warn(f"任务栏进度：所有创建路径失败，最后 hr={_hr_text(hr)}")
                return

            # 必须用方式 cast(p, POINTER(POINTER(c_void_p))).contents 读取 vtable：
            # cast(ptr.value, POINTER(c_void_p)) 在部分 Python 3.13 + ctypes 上
            # 会按错误偏移解引用，读出垃圾地址，导致后续调用崩溃或无效。
            table = cast(ptr, POINTER(POINTER(c_void_p))).contents
            self._tb = ptr

            def _addr(index: int) -> int:
                item = table[index]
                if item is None:
                    return 0
                return item if isinstance(item, int) else int(item.value)

            # IUnknown: 0/1/2；ITaskbarList: HrInit=3, AddTab=4；
            # ITaskbarList2: MarkFullscreenWindow=8；
            # ITaskbarList3: SetProgressValue=9, SetProgressState=10
            self._hr_init = WINFUNCTYPE(c_int, c_void_p)(_addr(3))
            self._add_tab = WINFUNCTYPE(c_int, c_void_p, c_void_p)(_addr(4))
            self._set_value = WINFUNCTYPE(
                c_int, c_void_p, c_void_p, c_ulonglong, c_ulonglong
            )(_addr(9))
            self._set_state = WINFUNCTYPE(
                c_int, c_void_p, c_void_p, c_int
            )(_addr(10))

            hr_init = self._hr_init(self._tb)
            log_info(f"任务栏进度：HrInit hr={_hr_text(hr_init)}")
            if hr_init < 0:
                self._clear()
                return

            # AddTab 仅用于多标签窗口共享任务栏按钮，普通主窗口按官方示例
            # HrInit 后即可直接 SetProgress*；这里只记录不阻断，避免副作用。
            if self._add_tab is not None:
                try:
                    hr_tab = self._add_tab(self._tb, c_void_p(self.hwnd))
                    log_info(f"任务栏进度：AddTab hwnd={self.hwnd} hr={_hr_text(hr_tab)}")
                except Exception as exc:
                    log_warn(f"任务栏进度：AddTab 异常 {exc!r}")

            self._ready = True
            self._path = path
            log_info(f"任务栏进度：初始化成功（{path}），hwnd={self.hwnd}")
        except Exception as exc:
            log_warn(f"任务栏进度：初始化异常 {exc!r}")
            self._clear()

    def _create_via_dll(self, windll, dllname: str):
        """绕过注册表，直接从系统 DLL 获取 IClassFactory 再创建 TaskbarList。"""
        try:
            dll = windll.LoadLibrary(dllname)
            fn = dll.DllGetClassObject
            fn.argtypes = [POINTER(GUID), POINTER(GUID), POINTER(c_void_p)]
            fn.restype = c_int
            factory = c_void_p()
            hr = fn(
                byref(CLSID_TaskbarList), byref(IID_IClassFactory), byref(factory)
            )
            if hr < 0 or not factory.value:
                return hr, c_void_p()
            # IClassFactory: QueryInterface=0, AddRef=1, Release=2, CreateInstance=3
            ftable = cast(factory, POINTER(POINTER(c_void_p))).contents

            def _faddr(index: int) -> int:
                item = ftable[index]
                if item is None:
                    return 0
                return item if isinstance(item, int) else int(item.value)

            create = WINFUNCTYPE(
                c_int, c_void_p, c_void_p, POINTER(GUID), POINTER(c_void_p)
            )(_faddr(3))
            ptr = c_void_p()
            hr = create(factory, None, byref(IID_ITaskbarList3), byref(ptr))
            release = WINFUNCTYPE(c_ulong, c_void_p)(_faddr(2))
            release(factory)
            return hr, ptr
        except Exception as exc:
            log_warn(f"任务栏进度：{dllname} 类工厂异常 {exc!r}")
            return -1, c_void_p()

    def _clear(self) -> None:
        self._tb = None
        self._add_tab = None
        self._set_value = None
        self._set_state = None
        self._hr_init = None
        self._ready = False

    # ------------------------------------------------------------------
    # 进度操作
    # ------------------------------------------------------------------
    def _ensure_ready(self) -> bool:
        """失败后在进度回调中做有限次重试，应对窗口/COM 尚未就绪的时序问题。"""
        if self._ready:
            return True
        if self.hwnd and self._retries < self._max_retries:
            self._retries += 1
            self._init_now()
        return self._ready

    def set_state(self, state: int) -> None:
        if not self._ensure_ready() or not self.hwnd or self._set_state is None:
            return
        try:
            hr = self._set_state(self._tb, c_void_p(self.hwnd), int(state))
            if hr < 0:
                log_warn(f"任务栏进度：SetProgressState({state}) 失败 hr={_hr_text(hr)}")
            else:
                log_info(f"任务栏进度：SetProgressState({state}) OK")
        except Exception as exc:
            log_warn(f"任务栏进度：SetProgressState 异常 {exc!r}")

    def set_value(self, value: int) -> None:
        if not self._ensure_ready() or not self.hwnd or self._set_value is None:
            return
        value = max(0, min(100, int(value)))
        try:
            hr = self._set_value(self._tb, c_void_p(self.hwnd), value, 100)
            if hr < 0:
                log_warn(f"任务栏进度：SetProgressValue({value}) 失败 hr={_hr_text(hr)}")
            elif value in (0, 50, 100):
                log_info(f"任务栏进度：SetProgressValue({value}) OK")
        except Exception as exc:
            log_warn(f"任务栏进度：SetProgressValue 异常 {exc!r}")

    def reset(self) -> None:
        if not self._ready:
            return
        self.set_state(self.TBPF_NOPROGRESS)
        try:
            if self._set_value is not None:
                self._set_value(self._tb, c_void_p(self.hwnd), 0, 100)
        except Exception:
            pass
