"""凭证管理器 — 密钥派生 + Fernet 对称加密。

专业做法：
- 首次启动时从机器硬件指纹生成密钥，保存到本地密钥文件
- 凭证 config 加密后存入数据库
- 列表返回遮蔽值，详情返回解密后的明文
"""
import os
import json
import base64
import uuid
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet


KEY_DIR: Optional[Path] = None
_fernet: Optional[Fernet] = None


def _get_key_dir() -> Path:
    global KEY_DIR
    if KEY_DIR is not None:
        return KEY_DIR
    # Prefer unified env naming, fallback to legacy env naming for compatibility.
    if os.environ.get("JINZHIHUILIAN_DATA_DIR"):
        KEY_DIR = Path(os.environ["JINZHIHUILIAN_DATA_DIR"])
    elif os.environ.get("JINZHIHUI_DATA_DIR"):
        KEY_DIR = Path(os.environ["JINZHIHUI_DATA_DIR"])
    elif os.environ.get("APPDATA"):
        KEY_DIR = Path(os.environ["APPDATA"]) / "jinzhihuilian"
    else:
        KEY_DIR = Path(__file__).resolve().parent.parent.parent.parent / "shared"
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    return KEY_DIR


def _get_key_path() -> Path:
    return _get_key_dir() / ".credential_key"


def _get_or_create_key() -> bytes:
    key_path = _get_key_path()
    if key_path.exists():
        with open(key_path, "rb") as f:
            return f.read()
    # Derive key from machine fingerprint (MAC address + CPU UUID)
    mac = uuid.getnode().to_bytes(6, byteorder="big").hex()
    cpu_id = os.environ.get("PROCESSOR_IDENTIFIER", "unknown")
    fingerprint = f"{mac}:{cpu_id}"
    raw = fingerprint.encode("utf-8")
    # Use PBKDF2-like derivation via base64
    import hashlib
    key_material = hashlib.sha256(raw).digest()
    key = base64.urlsafe_b64encode(key_material)
    with open(key_path, "wb") as f:
        f.write(key)
    # Restrict permissions on Windows
    try:
        import ctypes
        os.chmod(key_path, 0o600)
    except Exception:
        pass
    return key


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_get_or_create_key())
    return _fernet


def encrypt_credential(config: dict) -> str:
    """加密凭证配置，返回 base64 字符串。"""
    fernet = get_fernet()
    data = json.dumps(config, ensure_ascii=False).encode("utf-8")
    return fernet.encrypt(data).decode("utf-8")


def decrypt_credential(encrypted: str) -> dict:
    """解密凭证配置，返回 dict。"""
    fernet = get_fernet()
    data = fernet.decrypt(encrypted.encode("utf-8"))
    return json.loads(data.decode("utf-8"))


SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "apikey", "key_value", "bearer_token"}


def mask_sensitive(config: dict) -> dict:
    """遮蔽敏感配置值，用于列表返回。"""
    masked = {}
    for k, v in config.items():
        if k in SENSITIVE_KEYS:
            masked[k] = "***"
        elif isinstance(v, dict):
            masked[k] = mask_sensitive(v)
        else:
            masked[k] = v
    return masked
