"""
License 管理接口 — 合规设计：仅封装授权校验逻辑，不涉及第三方数据源。
"""
from typing import Optional, List


class LicenseManager:
    """
    License 授权管理器。提供功能权限校验、AI 生成次数查询等接口。

    合规说明：仅封装工具自身授权校验逻辑，不存储、不传输任何第三方数据源信息。
    """

    # 功能层级定义
    FEATURE_FREE = "free"
    FEATURE_PERSONAL = "personal"
    FEATURE_PROFESSIONAL = "professional"

    # 功能矩阵
    FEATURE_MATRIX = {
        "workflow_max": {"free": 1, "personal": 5, "professional": -1},
        "concurrent_tasks": {"free": 1, "personal": 5, "professional": -1},
        "ai_daily_limit": {"free": 3, "personal": -1, "professional": -1},
        "db_mysql": {"free": True, "personal": True, "professional": True},
        "db_sqlite": {"free": True, "personal": True, "professional": True},
        "db_duckdb": {"free": False, "personal": True, "professional": True},
        "db_postgresql": {"free": False, "personal": True, "professional": True},
        "db_clickhouse": {"free": False, "personal": False, "professional": True},
        "file_csv": {"free": True, "personal": True, "professional": True},
        "file_excel": {"free": False, "personal": True, "professional": True},
        "file_json": {"free": False, "personal": True, "professional": True},
        "file_parquet": {"free": False, "personal": True, "professional": True},
        "http_connector": {"free": False, "personal": True, "professional": True},
        "schedule_cron": {"free": False, "personal": True, "professional": True},
        "breakpoint_resume": {"free": False, "personal": True, "professional": True},
        "auto_retry": {"free": False, "personal": True, "professional": True},
        "advanced_script": {"free": False, "personal": True, "professional": True},
        "script_sandbox_full": {"free": False, "personal": True, "professional": True},
        "distributed_scheduler": {"free": False, "personal": False, "professional": True},
        "monitoring_alert": {"free": False, "personal": False, "professional": True},
        "backup_restore": {"free": False, "personal": False, "professional": True},
        "sdk_full_access": {"free": False, "personal": True, "professional": True},
    }

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lm = None
        return cls._instance

    def _get_core(self):
        """懒加载 license_manager 核心模块。"""
        if self._lm is None:
            try:
                from app.core import license_manager as lm
                self._lm = lm
            except ImportError:
                return None
        return self._lm

    def get_tier(self) -> str:
        """获取当前授权等级。"""
        core = self._get_core()
        if core is None:
            return self.FEATURE_FREE
        try:
            info = core.get_license_info()
            if info and info.get("activated"):
                return info.get("tier", self.FEATURE_FREE)
        except Exception:
            pass
        return self.FEATURE_FREE

    def check_feature(self, feature: str) -> bool:
        """检查功能是否可用。

        Args:
            feature: 功能名称（如 "db_duckdb", "ai_daily_limit"）
        Returns:
            True if available, False otherwise
        """
        tier = self.get_tier()
        matrix = self.FEATURE_MATRIX.get(feature, {})
        val = matrix.get(tier, False)
        if val == -1:  # unlimited
            return True
        return bool(val)

    def check_feature_or_raise(self, feature: str):
        """检查功能并抛出异常（不可用时）。"""
        if not self.check_feature(feature):
            raise PermissionError(
                f"功能 [{feature}] 需要更高授权等级。当前等级：{self.get_tier()}。"
                f"请升级至 Personal 或 Professional 版本。"
            )

    def get_ai_daily_remaining(self) -> int:
        """获取今日 AI 生成剩余次数。

        Returns:
            -1 表示无限制（付费版），0 表示已达上限，>0 表示剩余次数
        """
        if not self.check_feature("ai_daily_limit"):
            return 3  # free tier default
        core = self._get_core()
        if core is None:
            return -1
        try:
            return core.get_ai_daily_remaining()
        except Exception:
            return -1

    def increment_ai_count(self) -> int:
        """增加 AI 生成计数。返回剩余次数。"""
        core = self._get_core()
        if core is None:
            return 0
        try:
            return core.increment_ai_count()
        except Exception:
            return 0

    def get_machine_code(self) -> str:
        """获取本机机器码。"""
        core = self._get_core()
        if core is None:
            return ""
        try:
            return core.get_machine_code()
        except Exception:
            return ""

    def activate_online(self, code: str) -> dict:
        """在线激活 License。

        Args:
            code: 激活码
        Returns:
            {"success": bool, "message": str}
        """
        core = self._get_core()
        if core is None:
            return {"success": False, "message": "License 核心模块不可用"}
        try:
            return core.activate_online(code)
        except Exception as e:
            return {"success": False, "message": str(e)}

    def deactivate(self) -> dict:
        """解除当前设备授权。"""
        core = self._get_core()
        if core is None:
            return {"success": False, "message": "License 核心模块不可用"}
        try:
            core.clear_license()
            return {"success": True, "message": "已解除授权"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_license_info(self) -> dict:
        """获取当前授权详细信息。"""
        core = self._get_core()
        if core is None:
            return {
                "activated": False,
                "tier": self.FEATURE_FREE,
                "expires_at": None,
                "machine_code": "",
            }
        try:
            return core.get_license_info() or {}
        except Exception:
            return {"activated": False, "tier": self.FEATURE_FREE}
