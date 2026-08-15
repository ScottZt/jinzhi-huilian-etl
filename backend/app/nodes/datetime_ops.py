"""日期时间操作节点 — 格式化、计算、提取日期时间。"""
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class DateTimeOpsNode(BaseNode):
    node_type = "datetime_ops"
    display_name = "日期时间操作"
    category = "数据处理"
    params_schema = {
        "operation": {
            "type": "select",
            "label": "操作类型",
            "options": ["format", "extract", "add", "subtract", "diff", "parse", "now"],
            "default": "format",
            "placeholder": "选择要执行的日期时间操作"
        },
        "source_column": {
            "type": "text",
            "label": "源日期字段",
            "default": "dt",
            "placeholder": "包含日期时间的列名"
        },
        "target_column": {
            "type": "text",
            "label": "输出字段",
            "default": "",
            "placeholder": "结果保存到的列名（留空=覆盖源字段）"
        },
        "format": {
            "type": "text",
            "label": "日期格式",
            "default": "%Y-%m-%d %H:%M:%S",
            "placeholder": "format 操作: 输出格式；parse 操作: 输入格式"
        },
        "unit": {
            "type": "select",
            "label": "时间单位",
            "options": ["years", "months", "days", "hours", "minutes", "seconds"],
            "default": "days",
            "placeholder": "add/subtract/diff 操作的时间单位"
        },
        "value": {
            "type": "number",
            "label": "数值",
            "default": 1,
            "placeholder": "add/subtract 操作: 加/减的数量；diff 操作: 对比日期偏移"
        },
        "part": {
            "type": "select",
            "label": "提取部分",
            "options": ["year", "month", "day", "hour", "minute", "second", "weekday", "date", "time"],
            "default": "year",
            "placeholder": "extract 操作: 要提取的日期部分"
        },
        "target_date": {
            "type": "text",
            "label": "目标日期",
            "default": "",
            "placeholder": "diff 操作: 对比的目标日期（留空=当前时间）"
        },
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        执行日期时间操作。
        """
        if df.empty:
            return df

        operation = params.get("operation", "format")
        source_column = params.get("source_column", "dt")
        target_column = params.get("target_column", "").strip() or source_column

        if source_column not in df.columns:
            logger.warning("DateTimeOpsNode: 源列 '%s' 不存在", source_column)
            return df

        # 转换源列为 datetime 类型
        try:
            dt_col = pd.to_datetime(df[source_column])
        except Exception as e:
            logger.error("DateTimeOpsNode: 日期转换失败: %s", e)
            return df

        result = None

        if operation == "format":
            # 格式化日期时间
            fmt = params.get("format", "%Y-%m-%d %H:%M:%S")
            result = dt_col.dt.strftime(fmt)

        elif operation == "extract":
            # 提取日期部分
            part = params.get("part", "year")
            result = self._extract_part(dt_col, part)

        elif operation == "add":
            # 加时间
            unit = params.get("unit", "days")
            value = int(params.get("value", 1))
            result = self._add_time(dt_col, unit, value)

        elif operation == "subtract":
            # 减时间
            unit = params.get("unit", "days")
            value = int(params.get("value", 1))
            result = self._add_time(dt_col, unit, -value)

        elif operation == "diff":
            # 计算时间差
            unit = params.get("unit", "days")
            target_date = params.get("target_date", "").strip()
            result = self._calc_diff(dt_col, unit, target_date)

        elif operation == "parse":
            # 解析日期字符串
            fmt = params.get("format", "")
            if fmt:
                result = pd.to_datetime(df[source_column], format=fmt)
            else:
                result = pd.to_datetime(df[source_column])

        elif operation == "now":
            # 当前时间
            result = pd.Series([datetime.now()] * len(df))

        else:
            logger.warning("DateTimeOpsNode: 未知操作 '%s'", operation)
            return df

        # 保存结果
        if result is not None:
            df[target_column] = result

        return df

    def _extract_part(self, dt_col: pd.Series, part: str) -> pd.Series:
        """提取日期部分。"""
        if part == "year":
            return dt_col.dt.year
        elif part == "month":
            return dt_col.dt.month
        elif part == "day":
            return dt_col.dt.day
        elif part == "hour":
            return dt_col.dt.hour
        elif part == "minute":
            return dt_col.dt.minute
        elif part == "second":
            return dt_col.dt.second
        elif part == "weekday":
            return dt_col.dt.weekday  # 0=Monday, 6=Sunday
        elif part == "date":
            return dt_col.dt.date
        elif part == "time":
            return dt_col.dt.time
        else:
            logger.warning("DateTimeOpsNode: 未知部分 '%s'", part)
            return dt_col

    def _add_time(self, dt_col: pd.Series, unit: str, value: int) -> pd.Series:
        """加减时间。"""
        if unit == "years":
            # pandas 不支持直接加年份，使用 DateOffset
            return dt_col + pd.DateOffset(years=value)
        elif unit == "months":
            return dt_col + pd.DateOffset(months=value)
        elif unit == "days":
            return dt_col + pd.Timedelta(days=value)
        elif unit == "hours":
            return dt_col + pd.Timedelta(hours=value)
        elif unit == "minutes":
            return dt_col + pd.Timedelta(minutes=value)
        elif unit == "seconds":
            return dt_col + pd.Timedelta(seconds=value)
        else:
            logger.warning("DateTimeOpsNode: 未知单位 '%s'", unit)
            return dt_col

    def _calc_diff(self, dt_col: pd.Series, unit: str, target_date: str) -> pd.Series:
        """计算时间差。"""
        # 解析目标日期
        if target_date:
            try:
                target = pd.to_datetime(target_date)
            except Exception as e:
                logger.error("DateTimeOpsNode: 目标日期解析失败: %s", e)
                return pd.Series([0] * len(dt_col))
        else:
            target = pd.Timestamp.now()

        # 计算差值
        diff = target - dt_col

        # 转换单位
        if unit == "years":
            return (diff.days / 365.25).round(2)
        elif unit == "months":
            return (diff.days / 30.44).round(2)
        elif unit == "days":
            return diff.days
        elif unit == "hours":
            return (diff.total_seconds() / 3600).round(2)
        elif unit == "minutes":
            return (diff.total_seconds() / 60).round(2)
        elif unit == "seconds":
            return diff.total_seconds().round(2)
        else:
            logger.warning("DateTimeOpsNode: 未知单位 '%s'", unit)
            return diff.days
