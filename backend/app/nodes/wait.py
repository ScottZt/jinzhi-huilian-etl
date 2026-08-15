"""等待延时节点 — 暂停执行指定秒数。"""
import time
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class WaitNode(BaseNode):
    node_type = "wait"
    display_name = "等待延时"
    category = "流程控制"
    params_schema = {
        "seconds": {"type": "number", "label": "等待秒数", "default": 1,
                    "placeholder": "支持小数，例如 0.5 表示 500 毫秒"},
        "mode": {"type": "select", "label": "模式",
                 "options": ["delay", "until_timestamp"],
                 "default": "delay"},
        "target_timestamp": {"type": "text", "label": "目标时间戳（unix秒）",
                             "default": "",
                             "placeholder": "mode=until_timestamp 时填写"},
    }

    def process(self, df: pd.DataFrame, params: dict,
                context: Optional[dict] = None) -> pd.DataFrame:
        mode = params.get("mode", "delay")

        try:
            if mode == "delay":
                seconds = float(params.get("seconds", 1))
                if seconds > 0:
                    logger.info("WaitNode: 等待 %.2f 秒...", seconds)
                    time.sleep(seconds)
            elif mode == "until_timestamp":
                target = float(params.get("target_timestamp", 0))
                now = time.time()
                if target > now:
                    wait_seconds = target - now
                    logger.info("WaitNode: 等待到时间戳 %.0f（还需 %.2f 秒）...", target, wait_seconds)
                    time.sleep(wait_seconds)
                else:
                    logger.warning("WaitNode: 目标时间戳已过期，跳过等待")
            else:
                logger.warning("WaitNode: 未知 mode=%s，按 delay 处理", mode)
                seconds = float(params.get("seconds", 1))
                if seconds > 0:
                    time.sleep(seconds)

        except Exception as e:
            logger.error("WaitNode: 等待失败 - %s", e)

        # 原样返回 df
        return df
