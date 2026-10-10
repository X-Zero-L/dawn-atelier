"""Local HTTP host for adapters with confirmed scalar fields.

The host owns save selection, HTTP protections and plan review. Format rules,
discovery, capabilities and runtime restrictions stay in the selected adapter.
"""

import argparse
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

from app_paths import APP_ROOT, USER_ROOT, app_version
from atelier import Editor, Snapshot


class Workbench:
    def __init__(self, adapter, discover, runtime, root):
        self.adapter, self.discover, self.runtime = adapter, discover, runtime
        self.root = Path(root)
        self.editor = Editor(adapter, self.root / 'backups')
        self.exports = self.root / 'modified-saves'
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()

    def paths(self):
        return {hashlib.sha256(str(path.resolve()).casefold().encode()).hexdigest()[:24]: path
                for path in self.discover()}

    def selected(self, ident):
        path = self.paths().get(ident)
        if path is None or not path.is_file():
            raise ValueError('存档已不存在，请刷新列表后重新选择。')
        return path

    def saves(self):
        result = []
        paths = self.paths()
        for ident, path in paths.items():
            try:
                data = path.read_bytes()
                result.append({'id':ident, 'title':f'存档 {path.name}',
                               'modified':datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
                               'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()})
            except OSError as error:
                result.append({'id':ident,'title':f'存档 {path.name}','error':str(error),'modified':''})
        return sorted(result, key=lambda row:row['modified'], reverse=True)

    def save(self, ident):
        path = self.selected(ident)
        snapshot = Snapshot.capture(path)
        evidence = self.adapter.compatibility(snapshot)
        return {**self.adapter.inspect(snapshot.data), 'id':ident, 'title':f'存档 {path.name}',
                'sha256':snapshot.sha256, 'compatibility':evidence}

    def edit(self, body, mode=None):
        if not isinstance(body, dict):
            raise ValueError('修改请求格式无效。')
        source = self.selected(body.get('save'))
        snapshot = Snapshot.capture(source)
        if snapshot.sha256 != body.get('sha256'):
            raise ValueError('游戏已保存新的进度，请重新读取存档后再预览。')
        operations = body.get('operations')
        if not isinstance(operations, list) or not 1 <= len(operations) <= 1000:
            raise ValueError('请选择 1 至 1000 项已确认的修改。')
        plan = self.editor.preview(snapshot, operations)
        before = {row['id']:row for row in json.loads(plan.before_json)['fields']}
        after = {row['id']:row for row in json.loads(plan.after_json)['fields']}
        changes = [{'target':key, 'label':row['label'], 'before':row['value'], 'after':after[key]['value']}
                   for key,row in before.items() if row['value'] != after[key]['value']]
        result = {'plan_id':plan.plan_id, 'changes':changes, 'count':len(changes), 'bytes':len(plan.modified)}
        if mode:
            if body.get('plan_id') != plan.plan_id:
                raise ValueError('修改方案已变化，请重新预览后再保存。')
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            target = source if mode == 'apply' else self.exports / f'{source.name}-{stamp}.save'
            with self.lock:
                report = self.editor.commit(plan, target, approval=body['plan_id'], mode=mode)
            result.update(filename=target.name, backup=Path(report['backup']).name,
                          download=f'/downloads/{target.name}' if mode=='export' else None)
            if report.get('audit_error') or report.get('warnings'):
                result['warning'] = '存档和备份已保存，但操作记录或临时文件清理未完成，请查看本地数据目录。'
        return result

    def history(self):
        files = [{'name':path.name,'download':'/downloads/'+path.name,'bytes':path.stat().st_size,
                  'modified':datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds')}
                 for path in self.exports.glob('*.save')]
        history = []
        for path in sorted(self.editor.backup_root.glob('*.bak.json'), key=lambda p:p.stat().st_mtime, reverse=True)[:50]:
            try:
                report=json.loads(path.read_text(encoding='utf-8'))
                backup=Path(report['backup']).name
                if not (self.editor.backup_root/backup).is_file():
                    continue
                history.append({'backup':backup,'backup_download':'/backups/'+backup,'mode':report['mode'],
                                'created':report.get('recorded_at'),'count':len(report['operations'])})
            except (OSError,ValueError,KeyError):
                continue
        return {'files':sorted(files,key=lambda x:x['modified'],reverse=True),'history':history}


class Handler(BaseHTTPRequestHandler):
    server_version = 'AtelierWorkbench/1'

    def log_message(self, *_):
        pass

    @property
    def app(self):
        return self.server.workbench

    def host_valid(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def send(self, data, mime='application/json; charset=utf-8', status=200, attachment=None):
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        ancestor=getattr(self.server,'desktop_origin',None) or "'none'"
        self.send_header('Content-Security-Policy',f"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors {ancestor}; base-uri 'none'")
        if attachment:
            self.send_header('Content-Disposition',f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, status=200):
        self.send(json.dumps(value,ensure_ascii=False,allow_nan=False).encode(),status=status)

    def do_GET(self):
        if not self.host_valid():
            self.json({'error':'请通过本机工作台访问。'},403)
            return
        route=urlparse(self.path)
        query=parse_qs(route.query)
        try:
            if route.path=='/api/health':
                self.json({'app':'dawn-atelier','ready':True,'demo':self.app.adapter.descriptor.synthetic,'game':self.app.adapter.descriptor.id})
            elif route.path=='/api/bootstrap':
                self.json({'app':'dawn-atelier','version':app_version(),'token':self.app.token,
                           'game':self.app.adapter.descriptor.to_dict(),'saves':self.app.saves(),
                           'presets':getattr(self.app.adapter,'presets',[]),'notes':getattr(self.app.adapter,'notes',[]),
                           'runtime':self.app.runtime(),'desktop_origin':getattr(self.server,'desktop_origin',None),'demo':self.app.adapter.descriptor.synthetic})
            elif route.path=='/api/saves':
                self.json({'saves':self.app.saves()})
            elif route.path=='/api/save':
                self.json(self.app.save(query.get('id',[''])[0]))
            elif route.path=='/api/runtime':
                self.json(self.app.runtime())
            elif route.path=='/api/exports':
                self.json(self.app.history())
            elif route.path.startswith(('/downloads/','/backups/')):
                filename=route.path.rsplit('/',1)[-1]
                is_backup=route.path.startswith('/backups/')
                pattern=r'\d+\.\d{8}-\d{6}-\d{6}\.bak' if is_backup else r'\d+-\d{8}-\d{6}-\d{6}\.save'
                if not re.fullmatch(pattern,filename):
                    raise ValueError('文件名无效。')
                root=self.app.editor.backup_root if is_backup else self.app.exports
                path=root/filename
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('文件路径无效。')
                original_name=filename.split('.',1)[0] if is_backup else filename.split('-',1)[0]
                self.send(path.read_bytes(),'application/octet-stream',attachment=original_name)
            else:
                names={'/':'game.html','/game.js':'game.js','/game.css':'game.css','/brand/emblem.svg':'brand/emblem.svg'}
                relative=names.get(route.path)
                if relative is None:
                    self.json({'error':'页面不存在。'},404)
                    return
                path=APP_ROOT/'web'/relative
                self.send(path.read_bytes(),(mimetypes.guess_type(path.name)[0] or 'text/plain')+'; charset=utf-8')
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:
            self.json({'error':str(error)},400)

    def do_POST(self):
        if self.path=='/api/desktop-stop' and getattr(self.server,'desktop_token',None):
            if not self.host_valid() or not secrets.compare_digest(self.headers.get('X-Dawn-Control',''),self.server.desktop_token):
                self.json({'error':'无效桌面会话。'},403)
                return
            self.server.stopping=True
            self.json({'ok':True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()
            return
        if getattr(self.server,'stopping',False):
            self.json({'error':'工作台正在关闭。'},503)
            return
        origins=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
        if not self.host_valid() or self.headers.get('Origin') not in origins or self.headers.get('X-Dawn-Token')!=self.app.token:
            self.json({'error':'请在本地工作台执行此操作。'},403)
            return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1_000_000:
                raise ValueError('请求过大或为空。')
            body=json.loads(self.rfile.read(length))
            if self.path not in ('/api/preview','/api/export','/api/apply'):
                self.json({'error':'操作不存在。'},404)
                return
            self.json(self.app.edit(body,None if self.path=='/api/preview' else self.path.rsplit('/',1)[-1]))
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as error:
            self.json({'error':str(error)},400)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',choices=('blazblue',),default='blazblue')
    parser.add_argument('--port',type=int,default=18768)
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--demo',action='store_true',help='Use synthetic example saves only')
    parser.add_argument('--ready-file',type=Path)
    parser.add_argument('--fallback-port',action='store_true')
    args=parser.parse_args()
    from blazblue_adapter import BlazBlueAdapter, discover_saves, runtime_status
    if args.demo:
        from blazblue_demo import BlazBlueDemoAdapter, prepare
        root=USER_ROOT/'data/demo-games'/args.game
        path=prepare(root/'saves')
        app=Workbench(BlazBlueDemoAdapter(),lambda:[path],lambda:{'can_apply':False,'running':False,'message':'演示模式：仅可导出合成副本。'},root)
    else:
        app=Workbench(BlazBlueAdapter(),discover_saves,runtime_status,USER_ROOT/'data/games'/args.game)
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        if not args.fallback_port:
            raise
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.workbench=app
    server.daemon_threads=False
    server.desktop_token=secrets.token_urlsafe(32) if args.ready_file else None
    origin=os.environ.get('DAWN_DESKTOP_ORIGIN','')
    server.desktop_origin=origin if args.ready_file and re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}',origin) else None
    if args.ready_file:
        args.ready_file.parent.mkdir(parents=True,exist_ok=True)
        args.ready_file.write_text(json.dumps({'port':server.server_port,'pid':os.getpid(),'token':server.desktop_token,
                                              'session':os.environ.get('DAWN_DESKTOP_SESSION')}),encoding='utf-8')
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{server.server_port}')
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__=='__main__':
    main()
