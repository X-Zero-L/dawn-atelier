"""Read-only Windows process presence check without game configuration."""

import ctypes
from ctypes import wintypes
import os


def process_status(executable):
    unknown={'running':None,'can_apply':False,'message':'无法确认游戏运行状态，可以导出副本。'}
    if os.name!='nt':
        return unknown
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
    if handle==ctypes.c_void_p(-1).value:
        return unknown
    try:
        entry=Entry();entry.dwSize=ctypes.sizeof(entry)
        if not kernel.Process32FirstW(handle,ctypes.byref(entry)):
            return unknown
        while True:
            if entry.szExeFile.casefold()==executable.casefold():
                return {'running':True,'can_apply':False,'message':'游戏运行中，可导出副本；退出游戏后才能直接应用。'}
            if not kernel.Process32NextW(handle,ctypes.byref(entry)):
                if ctypes.get_last_error()!=18:
                    return unknown
                return {'running':False,'can_apply':True,'message':'游戏已退出，可先备份再应用到所选存档。'}
    finally:
        kernel.CloseHandle(handle)
