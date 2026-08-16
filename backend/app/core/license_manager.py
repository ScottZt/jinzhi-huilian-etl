"""License 授权管理系统 — 机器码绑定 + 在线/离线激活 + 版本权限控制。

签名验证使用 Ed25519 非对称加密：
  - 私钥签名：在闭源仓库中，仅开发者持有
  - 公钥验证：在此文件中，所有用户可见
  - 因此开源用户无法伪造激活码
"""
import hashlib
import hmac
import platform
import uuid
import json
import time
import os
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# ---- Activation code verification (Ed25519 public key) ----
# 公钥用于验证激活码签名，私钥在闭源仓库中
# 此公钥无法用于生成激活码，仅用于验证
_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAyskopTjdzLHdDnNBkyvGzT68qB/oHejiQ+KLYqA4eDM=
-----END PUBLIC KEY-----"""


def _verify_activation(lic_type: str, expires: str, signature: str) -> bool:
    """验证 Ed25519 签名。"""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization

        # 加载公钥
        public_key = serialization.load_pem_public_key(_PUBLIC_KEY_PEM)

        # 解码签名（hex -> bytes）
        sig_bytes = bytes.fromhex(signature)

        # 构造待验证的消息
        message = f"{lic_type}:{expires}".encode("utf-8")

        # 验证签名（失败会抛出异常）
        public_key.verify(sig_bytes, message)
        return True
    except Exception:
        return False


LICENSE_DB_KEY = "_license_meta"


def is_dev_mode() -> bool:
    """是否为开发者模式（跳过所有 License 检查）。"""
    return os.environ.get("JZHL_DEV_MODE", "").strip().lower() in ("true", "1", "yes")


class LicenseType:
    FREE = "free"
    PERSONAL = "personal"
    PROFESSIONAL = "professional"


LICENSE_FEATURES = {
    LicenseType.FREE: {
        "max_workflows": 1,
        "db_types": ["mysql", "sqlite"],
        "file_types": ["csv", "txt"],
        "ai_script_gen_daily": 3,
        "ai_optimize": False,
        "breakpoint_resume": False,
        "concurrent_tasks": 1,
        "background_run": False,
        "http_connector": False,
        "advanced_cleaning": False,
        "batch_script_generate": False,
        "distributed_scheduler": False,
        "advanced_monitoring": False,
        "backup_recovery": False,
        "pro_support": False,
        "pro_content_import": False,
    },
    LicenseType.PERSONAL: {
        "max_workflows": 5,
        "db_types": ["mysql", "sqlite", "duckdb", "postgresql"],
        "file_types": ["csv", "txt", "excel", "json", "parquet", "binary"],
        "ai_script_gen_daily": -1,
        "ai_optimize": True,
        "breakpoint_resume": True,
        "concurrent_tasks": 5,
        "background_run": True,
        "http_connector": True,
        "advanced_cleaning": True,
        "batch_script_generate": False,
        "distributed_scheduler": False,
        "advanced_monitoring": False,
        "backup_recovery": False,
        "pro_support": False,
        "pro_content_import": True,
    },
    LicenseType.PROFESSIONAL: {
        "max_workflows": -1,
        "db_types": ["mysql", "sqlite", "duckdb", "postgresql", "clickhouse"],
        "file_types": ["csv", "txt", "excel", "json", "parquet", "binary"],
        "ai_script_gen_daily": -1,
        "ai_optimize": True,
        "breakpoint_resume": True,
        "concurrent_tasks": -1,
        "background_run": True,
        "http_connector": True,
        "advanced_cleaning": True,
        "batch_script_generate": True,
        "distributed_scheduler": True,
        "advanced_monitoring": True,
        "backup_recovery": True,
        "pro_support": True,
        "pro_content_import": True,
    },
}


def get_machine_code() -> str:
    """生成设备机器码（CPU序列号 + 主板序列号 + 网卡MAC组合哈希）。"""
    factors = []

    # CPU ID
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True, text=True, timeout=5
            )
            cpu_id = result.stdout.strip().split("\n")[-1].strip()
            if cpu_id:
                factors.append(cpu_id)
        else:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "Serial" in line or "processor" in line:
                        factors.append(line.strip()[:32])
    except Exception:
        pass

    # Volume serial (Windows)
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_volume", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=5
            )
            vol = result.stdout.strip().split("\n")[-1].strip()
            if vol:
                factors.append(vol)
    except Exception:
        pass

    # Hostname + username
    factors.append(platform.node())
    factors.append(os.environ.get("USERNAME", ""))
    factors.append(os.environ.get("USER", ""))

    combined = "|".join(str(f) for f in factors if f)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32].upper()


def get_license_info() -> dict:
    """返回当前授权状态。

    开源模式：所有用户视为 professional，全部功能开放。
    仍保留数据库读取，以便记录用户导入的内容包等元信息。
    """
    from app.persistence import sqlite_repo
    meta = sqlite_repo.get_metadata(LICENSE_DB_KEY)
    lic = None
    if meta:
        try:
            lic = json.loads(meta) if isinstance(meta, str) else meta
        except Exception:
            lic = None

    # 开源模式：固定返回 professional，确保所有功能门槛均通过
    return {
        "type": LicenseType.PROFESSIONAL,
        "machine_code": get_machine_code(),
        "expires_at": None,
        "activated_at": None,
        "features": LICENSE_FEATURES[LicenseType.PROFESSIONAL],
        "activated": False,
    }


def save_license(lic_type: str, expires_at: Optional[str] = None, offline_token: Optional[str] = None):
    """保存 License 信息。"""
    from app.persistence import sqlite_repo
    lic = {
        "type": lic_type,
        "machine_code": get_machine_code(),
        "activated_at": datetime.now().isoformat(),
        "expires_at": expires_at,
        "offline_token": offline_token,
    }
    sqlite_repo.save_metadata(LICENSE_DB_KEY, json.dumps(lic, ensure_ascii=False))


def clear_license():
    """清除 License（解绑）。"""
    from app.persistence import sqlite_repo
    sqlite_repo.delete_metadata(LICENSE_DB_KEY)


def check_feature(feature: str) -> bool:
    """检查功能是否可用。

    开源模式：所有功能对全体用户开放，付费仅用于支持官方精选内容包。
    如需恢复分级授权，可将下方 `return True` 改回原实现。
    """
    return True


def check_feature_or_raise(feature: str):
    """检查功能，不支持则抛出异常（当前模式恒通过）。"""
    return True


def get_ai_daily_remaining() -> int:
    """获取今日剩余 AI 脚本生成次数。"""
    info = get_license_info()
    features = info.get("features", {})
    daily_limit = features.get("ai_script_gen_daily", 3)
    if daily_limit < 0:
        return -1  # 无限制

    # 检查每日计数
    key = f"_ai_gen_count_{datetime.now().strftime('%Y%m%d')}"
    from app.persistence import sqlite_repo
    count = sqlite_repo.get_metadata(key) or "0"
    remaining = daily_limit - int(count)
    return max(0, remaining)


def increment_ai_count():
    """AI 脚本生成计数 +1。"""
    key = f"_ai_gen_count_{datetime.now().strftime('%Y%m%d')}"
    from app.persistence import sqlite_repo
    current = int(sqlite_repo.get_metadata(key) or "0")
    sqlite_repo.save_metadata(key, str(current + 1))


def activate_online(activation_code: str) -> dict:
    """在线激活 License。"""
    machine_code = get_machine_code()

    # 激活码格式: {type}:{expires}:{hmac_signature}
    parts = activation_code.strip().split(":")
    if len(parts) < 3:
        raise ValueError("激活码格式无效（缺少签名）")

    lic_type = parts[0]
    expires_str = parts[1]
    signature = parts[2]

    if lic_type not in (LicenseType.PERSONAL, LicenseType.PROFESSIONAL):
        raise ValueError(f"不支持的 License 类型: {lic_type}")

    # HMAC-SHA256 签名验证
    if not _verify_activation(lic_type, expires_str, signature):
        raise PermissionError("激活码签名无效，请使用合法授权码")

    expires_at = None
    if expires_str and expires_str != "lifetime":
        try:
            dt = datetime.strptime(expires_str, "%Y-%m-%d")
            if dt <= datetime.now():
                raise ValueError("激活码已过期")
            expires_at = dt.isoformat()
        except ValueError:
            raise

    save_license(lic_type, expires_at)
    return get_license_info()


def activate_offline(lic_file_path: str) -> dict:
    """离线激活 — 验证 .lic 文件并导入。"""
    lic_file = Path(lic_file_path)
    if not lic_file.exists():
        raise FileNotFoundError("授权文件不存在")

    try:
        with open(lic_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise ValueError("授权文件格式错误")

    lic_type = data.get("type")
    machine_codes = data.get("machine_codes", [])
    expires_at = data.get("expires_at")
    current_mc = get_machine_code()

    if lic_type not in (LicenseType.PERSONAL, LicenseType.PROFESSIONAL):
        raise ValueError(f"不支持的 License 类型: {lic_type}")

    if machine_codes and current_mc not in machine_codes:
        raise PermissionError("此授权文件不包含当前设备的机器码，请在授权设备上使用")

    save_license(lic_type, expires_at, offline_token=data.get("token"))
    return get_license_info()


def export_offline_request() -> dict:
    """导出离线解绑请求（生成请求文件，发给客服获取 .lic）。"""
    machine_code = get_machine_code()
    current = get_license_info()
    return {
        "machine_code": machine_code,
        "current_type": current["type"],
        "request_at": datetime.now().isoformat(),
        "platform": platform.system(),
    }
