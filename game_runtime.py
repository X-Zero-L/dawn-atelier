"""Read-only process presence check used before replacing an on-disk game save."""

import ctypes
from ctypes import wintypes
import os
import time
from app_config import DEMO

_cached = (0, None)


def status(fresh=False):
    global _cached
    if DEMO:
        return {'running':False,'can_apply':False,'message':'演示模式：可导出演示副本，不会访问游戏存档。'}
    now=time.monotonic()
    if not fresh and now-_cached[0]<1:
        return dict(_cached[1])
    result={'running':None,'can_apply':False,'message':'无法确认游戏运行状态，可以导出修改副本。'}
    if os.name!='nt':return result
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
                  ('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
                  ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),
                  ('szExeFile',wintypes.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:return result
    try:
        entry=Entry();entry.dwSize=ctypes.sizeof(entry)
        more=kernel.Process32FirstW(handle,ctypes.byref(entry))
        if not more:return result
        running=False
        while more:
            if entry.szExeFile.casefold()=='thepiper.exe':running=True;break
            more=kernel.Process32NextW(handle,ctypes.byref(entry))
        result={'running':running,'can_apply':not running,
                'message':'游戏运行中，可导出副本；退出游戏后可直接应用。' if running else '游戏已退出，可备份后直接应用到所选存档。'}
        _cached=(now,result)
        return dict(result)
    finally:
        kernel.CloseHandle(handle)
