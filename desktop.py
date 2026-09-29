"""Windows desktop entry point and fixed subprocess tasks for the packaged app."""

import argparse
import json
import os
from pathlib import Path
import sys


def internal_task(name, arguments):
    # Frozen --windowed applications have no standard streams. Use real handles
    # so extractor output still reaches the parent process's captured log.
    def inherited_output(number):
        try:
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                import msvcrt
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.GetStdHandle.argtypes = [wintypes.DWORD]
                kernel.GetStdHandle.restype = wintypes.HANDLE
                handle = kernel.GetStdHandle(-11 if number == 1 else -12)
                if not handle or handle == ctypes.c_void_p(-1).value:
                    raise OSError('No redirected standard handle.')
                number = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
            return open(number, 'w', encoding='utf-8', errors='replace', closefd=False, buffering=1)
        except OSError:
            return open(os.devnull, 'w', encoding='utf-8')
    if sys.stdout is None:
        sys.stdout = inherited_output(1)
    if sys.stderr is None:
        sys.stderr = inherited_output(2)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    root = Path(__file__).resolve().parent
    sys.path[:0] = [str(root / 'research/bundles'), str(root / 'research')]
    sys.argv = [name, *arguments]
    if name == 'serve':
        from web_server import main
    elif name == 'prepare':
        from prepare import main
    elif name == 'unpack':
        from unpack import main
    elif name == 'catalogue':
        from export_catalogue import main
    elif name == 'art':
        from extract_web_art import main
    else:
        raise SystemExit('Unknown internal task.')
    main()


def has_webview_runtime():
    if os.name != 'nt':
        return False
    import winreg
    clients = (r'SOFTWARE\Microsoft\EdgeUpdate\Clients', r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients')
    runtime = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for parent in clients:
            try:
                with winreg.OpenKey(hive, parent + '\\' + runtime) as key:
                    version, _ = winreg.QueryValueEx(key, 'pv')
                    if version and version != '0.0.0.0':
                        return True
            except OSError:
                pass
    return False


def instance_guard(directory):
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    import hashlib
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    identity = hashlib.sha256(str(directory.resolve()).casefold().encode()).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, False, 'Local\\DawnAtelier-' + identity)
    if not handle:
        raise OSError(ctypes.get_last_error(), '无法创建桌面会话。')
    if ctypes.get_last_error() == 183:
        ctypes.windll.user32.MessageBoxW(None, '黎明工坊已经打开，请从任务栏切回现有窗口。', '黎明工坊', 0x40)
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(handle)
        raise SystemExit(0)
    return handle


def browser_fallback(service):
    """A small native launcher remains available without the WebView2 runtime."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    import webbrowser
    app = tk.Tk()
    app.title('黎明工坊 · 启动')
    app.geometry('650x480')
    app.minsize(570, 430)
    app.configure(bg='#f6f3e9')
    tk.Label(app, text='黎明工坊', bg='#f6f3e9', fg='#203e34', font=('Microsoft YaHei UI', 26, 'bold')).pack(anchor='w', padx=32, pady=(28, 6))
    tk.Label(app, text='《黎明门前的吹笛人》存档工具', bg='#f6f3e9', fg='#697b68', font=('Microsoft YaHei UI', 11)).pack(anchor='w', padx=34)
    tk.Label(app, text='当前使用浏览器模式。安装 Microsoft WebView2 后可使用独立窗口。',
             bg='#f6f3e9', fg='#697b68', wraplength=575, justify='left').pack(anchor='w', padx=34, pady=(22, 14))
    row = tk.Frame(app, bg='#f6f3e9')
    row.pack(fill='x', padx=34)
    chosen = tk.StringVar(value=service.status()['game_dir'])
    entry = ttk.Entry(row, textvariable=chosen)
    entry.pack(side='left', fill='x', expand=True, ipady=6)
    def choose():
        value = filedialog.askdirectory(title='选择包含 ThePiper.exe 的游戏目录')
        if value:
            chosen.set(value)
    ttk.Button(row, text='选择游戏', command=choose).pack(side='right', padx=(10, 0))
    status = tk.StringVar(value='选择游戏目录，或直接体验演示。')
    tk.Label(app, textvariable=status, bg='#f6f3e9', fg='#203e34', wraplength=575, justify='left').pack(anchor='w', padx=34, pady=20)
    progress = ttk.Progressbar(app, maximum=100)
    progress.pack(fill='x', padx=34)
    pending = {'start_after_prepare': False, 'opened': None, 'error': None}
    def begin(mode):
        try:
            if mode == 'game':
                service.set_game(chosen.get())
                if not service.status()['prepared']:
                    pending['start_after_prepare'] = True
                    service.prepare()
                    return
            service.launch(mode)
        except Exception as exc:
            messagebox.showerror('尚未打开工坊', str(exc), parent=app)
    buttons = tk.Frame(app, bg='#f6f3e9')
    buttons.pack(fill='x', padx=34, pady=24)
    start = ttk.Button(buttons, text='准备并打开工坊', command=lambda: begin('game'))
    start.pack(side='left', padx=(0, 12))
    demo = ttk.Button(buttons, text='体验演示', command=lambda: begin('demo'))
    demo.pack(side='left')
    ttk.Button(buttons, text='安装 WebView2', command=lambda: webbrowser.open('https://developer.microsoft.com/microsoft-edge/webview2/')).pack(side='right')
    ttk.Button(app, text='打开数据与备份文件夹', command=lambda: service.open_folder('data')).pack(anchor='w', padx=34)
    def refresh():
        current = service.check_game_update()
        update = current.get('game_update', {})
        if not current['busy'] and not current['active_url'] and update.get('phase') == 'ready':
            current = service.refresh_game_update(update['token'])
        status.set(current['error'] or (update.get('message') if update.get('phase') in ('waiting', 'ready') else '') or current['progress']['message'])
        progress['value'] = current['progress']['percent']
        start['state'] = demo['state'] = 'disabled' if current['busy'] else 'normal'
        if not current['busy'] and pending['start_after_prepare']:
            pending['start_after_prepare'] = False
            if current['prepared'] and not current['error']:
                service.launch('game')
        if current['active_url'] and pending['opened'] != current['active_url']:
            pending['opened'] = current['active_url']
            service.open_browser()
            status.set('工坊已在浏览器打开，使用期间请保持这个窗口开启。')
        app.after(700, refresh)
    def close():
        if service.status()['busy']:
            messagebox.showinfo('请稍候', '当前正在准备或启动工坊，完成后即可关闭。', parent=app)
            return
        if service.status()['active_url'] and not messagebox.askyesno('关闭工坊', '关闭启动器会结束当前工作台服务。未保存修改会保留为草稿，确定关闭？', parent=app):
            return
        try:
            service._close()
            app.destroy()
        except Exception as exc:
            messagebox.showerror('工作台仍在运行', str(exc), parent=app)
    app.protocol('WM_DELETE_WINDOW', close)
    refresh()
    app.mainloop()


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--internal-task':
        try:
            internal_task(sys.argv[2], sys.argv[3:])
        except Exception:
            import traceback
            traceback.print_exc()
            raise SystemExit(1) from None
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Open the desktop in demonstration mode')
    parser.add_argument('--browser', action='store_true', help='Use the native browser-mode launcher')
    parser.add_argument('--home', type=Path, help='Use a separate workspace for this launch')
    args = parser.parse_args()
    if args.home:
        os.environ['DAWN_HOME'] = str(args.home.expanduser().resolve())
    from app_paths import APP_ROOT, USER_ROOT, LOG_ROOT, app_version
    from desktop_service import DesktopService
    session_handle = instance_guard(USER_ROOT)
    service = DesktopService()
    if args.browser or not has_webview_runtime():
        browser_fallback(service)
        return
    import logging
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(LOG_ROOT / 'desktop.log'), encoding='utf-8', level=logging.INFO)
    import webview
    webview.settings['ALLOW_DOWNLOADS'] = True
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
    # Each independent --home session must serve its own launcher resources.
    # pywebview otherwise shares port 42001 in persistent mode and may display
    # an older running copy's UI with this process's newer Python bridge.
    webview.settings['DEFAULT_HTTP_PORT'] = 0
    window = webview.create_window('黎明工坊 · 黎明门前的吹笛人', str(APP_ROOT / 'desktop/index.html'),
        js_api=service, width=1440, height=940, min_size=(1000, 700), background_color='#f6f3e9')
    service._window = window
    def closing(*_):
        if service.status()['busy']:
            window.create_confirmation_dialog('请稍候', '当前操作还在进行，完成后即可关闭。')
            return False
        if service.status()['active_url']:
            if not window.create_confirmation_dialog('关闭工坊', '确定关闭工坊？尚未保存的修改会保留为草稿。'):
                return False
        try:
            service._close()
        except Exception as exc:
            window.create_confirmation_dialog('请稍候', str(exc))
            return False
        return True
    window.events.closing += closing
    def startup():
        if args.demo:
            service.launch('demo')
    try:
        webview.start(startup, gui='edgechromium', private_mode=False,
                      storage_path=str(USER_ROOT / 'webview'), icon=str(APP_ROOT / 'build/assets/dawn-atelier.ico'),
                      localization={'global.quitConfirmation': '确定关闭工坊？', 'global.ok': '确定', 'global.cancel': '取消',
                                    'global.saveFile': '保存文件', 'global.openFiles': '选择文件', 'global.openFolder': '选择文件夹'})
    except Exception:
        logging.exception('Desktop window could not start; using native browser launcher.')
        service._window = None
        browser_fallback(service)


if __name__ == '__main__':
    main()
