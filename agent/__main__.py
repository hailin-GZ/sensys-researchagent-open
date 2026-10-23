import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web-redesign'))
from . import store
from . import models
from .engine import worker
p=argparse.ArgumentParser();p.add_argument('command',choices=['worker','dialog-worker','bootstrap']);p.add_argument('--credentials');a=p.parse_args()
store.init()
if a.command in ('worker','dialog-worker'):worker('dialog' if a.command=='dialog-worker' else 'research')
else:print(json.dumps(models.bootstrap(a.credentials),ensure_ascii=False))
