"""Create a fresh local encryption key without printing it."""
import os
from pathlib import Path
from cryptography.fernet import Fernet

root=Path(__file__).resolve().parents[1]
folder=root/'runtime/private';folder.mkdir(parents=True,exist_ok=True)
if os.name!='nt':folder.chmod(0o700)
path=folder/'secret.key'
if path.exists():
    print('Existing private key retained; no credential was rotated.')
else:
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(Fernet.generate_key()+b'\n')
    print('Created a fresh private encryption key.')
print('Set SENSYS_SECRET_KEY_FILE to the absolute path: '+str(path))
print('Set SENSYS_MODEL to the exact model identifier supplied by your provider.')
