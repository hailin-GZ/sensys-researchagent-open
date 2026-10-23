"""Pinned text-only method allowlist; no runtime downloading or code execution."""
import hashlib,json
from pathlib import Path
def selected(paths,skill):
    index=Path(skill)/'references/method-library.json'
    if not index.exists():return []
    rows={}
    for method in json.loads(index.read_text(encoding='utf-8'))['methods']:
        rows[method['path']]=method
        rows.update({x['path']:x for x in method.get('files',[]) if x['path'].endswith('.md')})
    out=[]
    for rel in paths:
        if rel not in rows:continue
        row=rows[rel];path=(Path(skill)/rel).resolve()
        if not path.is_relative_to(Path(skill).resolve()) or not path.is_file():raise ValueError('Bundled method missing')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Bundled method integrity check failed')
        out.append({'path':rel,'sha256':row['sha256']})
    return out
