"""Authenticated encryption for Linux; the key stays outside release packages."""
import os
import stat
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

PREFIX = 'fernet:v1:'

def cipher():
    value = os.environ.get('SENSYS_SECRET_KEY_FILE', '')
    path = Path(value)
    if not value or not path.is_absolute() or path.is_symlink():
        raise ValueError('Configure an absolute, private SENSYS_SECRET_KEY_FILE')
    # Open without following a last-component symlink and validate the opened file.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('The encryption key must be a regular file')
        if os.name != 'nt' and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise ValueError('The encryption key must be owned by the service user with mode 0600')
        key = handle.read(100).strip()
    return Fernet(key)

def encrypt(value):
    return PREFIX + cipher().encrypt(value.encode('utf-8')).decode('ascii')

def decrypt(value):
    if not value.startswith(PREFIX):
        raise ValueError('Windows credentials must be re-encrypted before Linux migration')
    try:
        return cipher().decrypt(value[len(PREFIX):].encode('ascii')).decode('utf-8')
    except InvalidToken:
        raise ValueError('The credential key is incorrect or the ciphertext was modified') from None
