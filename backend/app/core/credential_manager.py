"""凭证管理器 — 密钥派生 + Fernet 对称加密。

专业做法：
- 首次启动时从机器硬件指纹 + PBKDF2-HMAC-SHA256 派生密钥，保存到本地密钥文件
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
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# PBKDF2 参数 — 平衡安全性与启动性能
_PBKDF2_ITERATIONS = 200_000
_PBKDF2_SALT_LENGTH = 16

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
            content = f.read()
        # New format: "salt\nkey" or legacy: just "key"
        if b"\n" in content:
            _, key = content.split(b"\n", 1)
            return key
        return content
    # Derive key from machine fingerprint using PBKDF2-HMAC-SHA256
    mac = uuid.getnode().to_bytes(6, byteorder="big")
    cpu_id = os.environ.get("PROCESSOR_IDENTIFIER", "unknown").encode("utf-8")
    salt = os.urandom(_PBKDF2_SALT_LENGTH)
    raw = mac + cpu_id

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key_material = kdf.derive(raw)
    key = base64.urlsafe_b64encode(key_material)

    # Store key file with salt prepended (needed for re-derivation if key file is lost)
    with open(key_path, "wb") as f:
        f.write(salt + b"\n" + key)

    # Restrict permissions on Windows
    try:
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
