"""私有功能解锁鉴权。

通过本机环境变量配置密码，前端解锁成功后携带临时 Token 访问私有功能。
"""

import hmac
import os
import secrets
import time
from typing import Dict


# 请求头名称固定，前后端通过该头传递一次性解锁令牌。
PRIVATE_FEATURE_HEADER = "X-Private-Feature-Token"

# 仅为 Mootdx 私有功能使用的环境变量名称。
PRIVATE_FEATURE_PASSWORD_ENV = "JZHL_MOOTDX_PASSWORD"

# 解锁令牌默认有效期 12 小时，避免每次刷新页面都重新输入密码。
PRIVATE_FEATURE_TOKEN_TTL_SECONDS = 12 * 60 * 60

# 进程内保存临时令牌；应用重启后会自然失效。
_ACTIVE_TOKENS: Dict[str, float] = {}


def _cleanup_expired_tokens() -> None:
    """清理过期令牌，避免内存中的旧 Token 持续堆积。"""
    now = time.time()
    expired_tokens = [token for token, expires_at in _ACTIVE_TOKENS.items() if expires_at <= now]
    for token in expired_tokens:
        _ACTIVE_TOKENS.pop(token, None)


def is_private_feature_configured() -> bool:
    """判断私有功能密码是否已在环境变量中配置。"""
    return bool(str(os.environ.get(PRIVATE_FEATURE_PASSWORD_ENV, "")).strip())


def issue_private_feature_token(password: str) -> str:
    """校验密码并签发临时令牌。密码不正确时返回空字符串。"""
    expected_password = str(os.environ.get(PRIVATE_FEATURE_PASSWORD_ENV, "")).strip()
    provided_password = str(password or "").strip()
    if (not expected_password) or (not provided_password):
        return ""
    if not hmac.compare_digest(provided_password, expected_password):
        return ""

    _cleanup_expired_tokens()
    token = secrets.token_urlsafe(32)
    _ACTIVE_TOKENS[token] = time.time() + PRIVATE_FEATURE_TOKEN_TTL_SECONDS
    return token


def is_private_feature_token_valid(token: str) -> bool:
    """校验当前令牌是否有效。"""
    if not is_private_feature_configured():
        return False

    _cleanup_expired_tokens()
    expires_at = _ACTIVE_TOKENS.get(str(token or "").strip())
    if not expires_at:
        return False
    if expires_at <= time.time():
        _ACTIVE_TOKENS.pop(str(token or "").strip(), None)
        return False
    return True
