"""Start or reuse the local workbench, then open a browser."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen, build_opener, ProxyHandler
import webbrowser

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true',help='Use synthetic saves without an installed game')
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}'
    opener=build_opener(ProxyHandler({}))
    def state():
        try:
            with opener.open(url+'/api/health',timeout=1) as response:return json.load(response)
        except Exception:return None
    current=state()
    if current and (current.get('app')!='dawn-atelier' or bool(current.get('demo'))!=args.demo):
        raise SystemExit(f'Port {args.port} is serving another mode. Choose a different --port.')
    if not current:
        logdir=ROOT/'web/logs'
        logdir.mkdir(parents=True,exist_ok=True)
        command=[sys.executable,'-X','utf8',str(ROOT/'web_server.py'),'--port',str(args.port)]
        if args.demo:command.append('--demo')
        options={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {'start_new_session':True}
        with (logdir/'launcher.log').open('ab') as log:
            subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log,**options)
        for _ in range(60):
            if state():break
            time.sleep(.15)
    if not state():
        raise SystemExit('Workbench could not start. Run python prepare.py first, or use --demo. See web/logs/launcher.log.')
    print(url)
    if not args.no_browser:webbrowser.open(url)


if __name__=='__main__':main()
