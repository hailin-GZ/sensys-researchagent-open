"""Audit source filenames, text, data contracts, and every reachable Git blob.

This is one defense layer. Also run an independent scanner and a local comparison
against privately held credentials; never place those private values in this file.
"""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path

FORBIDDEN_PARTS={'runtime','private','data','.secrets','.venv','venv','node_modules','__pycache__'}
FORBIDDEN_SUFFIXES={'.sqlite','.sqlite3','.db','.pem','.key','.p12','.pfx','.pyc','.log','.zip','.gz','.7z','.exe','.dll','.so','.dylib','.apk','.keystore'}
PATTERNS={
    'private-key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'provider-token':re.compile(r'\bsk-[A-Za-z0-9_-]{18,}\b'),
    'github-token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'cloud-access-key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'personal-filesystem-path':re.compile(r'(?:(?i:[A-Z]:[\\/]+(?:Users|AI)[\\/]+[A-Za-z0-9_.-]+[\\/])|(?<![\w:/])/(?:home|Users)/[A-Za-z0-9_.-]+/)'),
}
def path_checks(name):
    p=Path(name);vendor=name.startswith('skills/sensys-market-research/vendor/')
    errors=[]
    if p.is_absolute() or '..' in p.parts:errors.append('unsafe-path')
    if any(x in FORBIDDEN_PARTS and not (vendor and x=='data') for x in p.parts):errors.append('private-or-generated-directory')
    if p.suffix.lower() in FORBIDDEN_SUFFIXES:errors.append('private-or-binary-artifact')
    if p.name.startswith('.env') and p.name!='.env.example':errors.append('environment-file')
    return errors
def scan(name,raw):
    errors=path_checks(name)
    if raw.startswith(b'SQLite'+b' format 3'):errors.append('database-header')
    if b'\x00' in raw:return errors+['binary-content']
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:return errors+['non-utf8-source']
    for rule,pattern in PATTERNS.items():
        if pattern.search(text):errors.append(rule)
    if re.search(r'[\u3400-\u9fff]',text):errors.append('non-english-source-text')
    return errors
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args])
def audit(root,history=True):
    root=Path(root).resolve();has_git=(root/'.git').is_dir()
    if has_git:names=[x.decode() for x in git(root,'ls-files','-z').split(b'\0') if x]
    else:names=[p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and not any(x in {'.git','__pycache__','runtime','data','.venv','node_modules'} and not (x=='data' and p.relative_to(root).as_posix().startswith('skills/sensys-market-research/vendor/')) for x in p.relative_to(root).parts)]
    findings=[];hashes={}
    for name in names:
        p=root/name
        if p.is_symlink():findings.append({'path':name,'rule':'symlink'});continue
        raw=p.read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
        findings.extend({'path':name,'rule':rule} for rule in scan(name,raw))
    blobs=0
    if has_git and history:
        result=subprocess.run(['git','-C',str(root),'rev-list','--objects','--all'],capture_output=True,check=True).stdout
        entries={}
        for row in result.splitlines():
            pair=row.split(b' ',1)
            if len(pair)==2:entries.setdefault(pair[0].decode(),pair[1].decode())
        if entries:
            batch=('\n'.join(entries)+'\n').encode()
            types=subprocess.run(['git','-C',str(root),'cat-file','--batch-check=%(objectname) %(objecttype)'],input=batch,capture_output=True,check=True).stdout
            ids=[line.split()[0].decode() for line in types.splitlines() if line.endswith(b' blob')]
            payload=('\n'.join(ids)+'\n').encode()
            stream=subprocess.run(['git','-C',str(root),'cat-file','--batch'],input=payload,capture_output=True,check=True).stdout
            position=0
            for oid in ids:
                end=stream.index(b'\n',position);size=int(stream[position:end].split()[-1]);raw=stream[end+1:end+1+size];position=end+size+2;blobs+=1
                findings.extend({'path':entries[oid],'rule':rule,'blob':oid} for rule in scan(entries[oid],raw))
    # Integrity of each bundled method and its supporting documents.
    skill=root/'skills/sensys-market-research';index=skill/'references/method-library.json'
    methods=json.loads(index.read_text(encoding='utf-8'))['methods']
    for method in methods:
        for item in [method,*method.get('files',[])]:
            p=(skill/item['path']).resolve()
            if not p.is_relative_to(skill.resolve()) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
                findings.append({'path':item['path'],'rule':'method-integrity'})
    return {'files':len(hashes),'historical_blobs':blobs,'method_documents':len(methods),'findings':findings,'passed':not findings,'tree_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',nargs='?',default='.');parser.add_argument('--no-history',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=audit(args.root,not args.no_history);text=json.dumps(result,indent=2)
    if args.output:args.output.write_text(text+'\n',encoding='utf-8')
    print(text);sys.exit(0 if result['passed'] else 1)
