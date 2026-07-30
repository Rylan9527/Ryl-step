# -*- coding: utf8 -*-
"""密码加密/解密服务，使用 cryptography Fernet 对称加密"""
import os
from cryptography.fernet import Fernet

KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'secret.key')


def _load_key() -> bytes:
    """加载或生成主密钥，持久化到 secret.key 文件"""
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as f:
            f.write(key)
        return key
    with open(KEY_FILE, 'rb') as f:
        return f.read()


_fernet = Fernet(_load_key())


def encrypt_password(plain: str) -> str:
    """加密明文密码，返回 base64 字符串"""
    return _fernet.encrypt(plain.encode('utf-8')).decode('utf-8')


def decrypt_password(cipher: str) -> str:
    """解密密码，返回明文"""
    return _fernet.decrypt(cipher.encode('utf-8')).decode('utf-8')
