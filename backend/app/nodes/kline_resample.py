"""K线任意分钟合成节点 — 把 1min 数据合成为任意分钟 K 线。

关键设计：不能直接用 pandas 的 resample(rule)，原因有二：
  1) resample 按绝对时间 floor，A 股午休 11:30-13:00 会被错误合并
     例如 90min 合成：11:00-12:30 会被当成一根 bar，但 11:30-13:00 没交易
  2) 用户想要"任意分钟"（3/7/13/90/120 等），不是写死的 5/15/30/60

解决思路：按 (code, date, session_idx, bar_idx) 分桶
  - session: 用户定义的交易时段，如 A 股 09:30-11:30、13:00-15:00
  - bar_idx = (time_of_day - session_start) // minutes
  - 这样跨午休绝对不会被合并，且支持任意分钟数
"""
import re
from datetime import datetime, time, date
import pandas as pd
from app.core.workflow_engine import BaseNode


# 预置市场时段模板（用户也可在 sessions 字段里自己写）
SESSION_PRESETS = {
    "a_stock": "09:30-11:30,13:00-15:00",        # A 股
    "a_stock_night": "21:00-23:00",               # A 股夜盘（股指期货）
    "futures_day": "09:00-10:15,10:30-11:30,13:30-15:00",  # 国内期货日盘
    "futures_night": "21:00-23:00",               # 期货夜盘（短/中时段品种）
    "futures_night_long": "21:00-02:30",          # 期货长夜盘（铜/铝等）
    "crypto_24h": "00:00-23:59",                  # 加密货币 24 小时
    "forex_24h": "00:00-23:59",                   # 外汇 24 小时
}

_SESSION_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def _parse_sessions(sessions_str: str) -> list[tuple[int, int]]:
    """解析时段字符串为 [(start_minutes, end_minutes), ...]。

    支持跨午夜色情：如 21:00-02:30 → (1260, 150+1440) 即 (1260, 1590)。
    """
    result = []
    for part in (sessions_str or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = _SESSION_RE.match(part)
        if not m:
            raise ValueError(f"时段格式错误：'{part}'，应为 HH:MM-HH:MM")
        sh, sm, eh, em = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        start = sh * 60 + sm
        end = eh * 60 + em
        # 跨午夜：结束时间加 24h
        if end <= start:
            end += 24 * 60
        result.append((start, end))
    # 按时段起始排序
    result.sort(key=lambda x: x[0])
    return result


def _assign_session_bar(time_minutes: int, sessions: list[tuple[int, int]],
                        minutes: int) -> tuple[int, int] | None:
    """返回 (session_idx, bar_idx)，或 None（不在任何时段）。

    bar_idx = (time_of_day - session_start) // minutes，同 bar_idx 的行聚合为一根 K 线。
    跨午夜场景：time_minutes 可能是当天 0-1440 范围内的值；如果 sessions 里有跨午夜
    的时段（end>1440），需要把 time_minutes 加上 24h 再判断。
    """
    for i, (s, e) in enumerate(sessions):
        if e <= 1440 and s <= time_minutes < e:
            return i, (time_minutes - s) // minutes
        # 跨午夜时段（如 21:00-02:30 → 1260-1590）
        if e > 1440:
            # 当天部分：time >= s
            if time_minutes >= s:
                return i, (time_minutes - s) // minutes
            # 次日凌晨部分：time < (e - 1440)
            if time_minutes < (e - 1440):
                return i, (time_minutes + 1440 - s) // minutes
    return None


def _bar_start_time(session_start: int, bar_idx: int, minutes: int) -> time:
    """根据 session 起始分钟和 bar 索引计算 bar 起始时刻。"""
    m = session_start + bar_idx * minutes
    # 跨午夜：回到 24h 内
    m = m % 1440
    return time(m // 60, m % 60)


class KlineResampleNode(BaseNode):
    node_type = "kline_resample"
    display_name = "K线任意分钟合成"
    category = "指标计算"
    params_schema = {
        "minutes": {
            "type": "number", "label": "目标分钟数（任意正整数）",
            "default": 5, "min": 1,
            "placeholder": "5/7/13/30/90/120 等任意值",
        },
        "time_column": {"type": "text", "label": "时间字段", "default": "dt"},
        "group_column": {"type": "text", "label": "分组字段（留空=整表单组）", "default": "code"},
        "mode": {
            "type": "select", "label": "对齐模式",
            "opts": [
                {"value": "session", "label": "按交易时段切分（A 股 / 期货推荐）"},
                {"value": "natural", "label": "自然分钟对齐（7x24 小时市场）"},
            ],
            "default": "session",
        },
        "sessions": {
            "type": "text", "label": "交易时段（逗号分隔）",
            "default": "09:30-11:30,13:00-15:00",
            "placeholder": "预设：a_stock / futures_day / crypto_24h / 或直接写 HH:MM-HH:MM,...",
        },
        "drop_incomplete": {
            "type": "checkbox", "label": "丢弃未完成的最后一根 bar（数据量 < 目标分钟数）",
            "default": True,
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        if df.empty:
            return df

        # ---- 参数解析 ----
        try:
            minutes = int(params.get("minutes") or 5)
        except (TypeError, ValueError):
            minutes = 5
        if minutes < 1:
            raise ValueError(f"目标分钟数必须 >= 1，当前：{minutes}")

        time_col = params.get("time_column") or "dt"
        group_col = (params.get("group_column") or "").strip()
        mode = params.get("mode") or "session"
        sessions_raw = (params.get("sessions") or "").strip()
        drop_incomplete = bool(params.get("drop_incomplete", True))

        if time_col not in df.columns:
            raise ValueError(f"找不到时间字段：'{time_col}'，可用字段：{list(df.columns)}")

        # ---- 时段解析 ----
        if mode == "session":
            # 支持预设名或直接写时段字符串
            sessions_str = SESSION_PRESETS.get(sessions_raw, sessions_raw)
            if not sessions_str:
                raise ValueError("交易时段不能为空（可用预设：a_stock / futures_day / crypto_24h）")
            sessions = _parse_sessions(sessions_str)
            if not sessions:
                raise ValueError(f"未能解析出任何时段：'{sessions_raw}'")

        # ---- 基础清洗 ----
        work = df.copy()
        work[time_col] = pd.to_datetime(work[time_col], errors="coerce")
        before = len(work)
        work = work.dropna(subset=[time_col])
        if work.empty:
            return work

        # ---- 分桶键计算 ----
        work["_date"] = work[time_col].dt.date
        work["_tod"] = work[time_col].dt.hour * 60 + work[time_col].dt.minute

        if mode == "session":
            # 每行 → (session_idx, bar_idx)，None 表示不在任何时段（将被丢弃）
            bucket = work["_tod"].apply(lambda t: _assign_session_bar(t, sessions, minutes))
            work["_session_idx"] = bucket.apply(lambda x: x[0] if x is not None else None)
            work["_bar_idx"] = bucket.apply(lambda x: x[1] if x is not None else None)
            work = work.dropna(subset=["_session_idx"])
            # bar_idx 转为整数（同 session 内从 0 起）
            work["_session_idx"] = work["_session_idx"].astype(int)
            work["_bar_idx"] = work["_bar_idx"].astype(int)
            agg_keys = ["_date", "_session_idx", "_bar_idx"]
        else:
            # 自然分钟对齐：直接 floor
            work["_bar_key"] = work[time_col].dt.floor(f"{minutes}min")
            agg_keys = ["_bar_key"]

        if group_col and group_col in work.columns:
            agg_keys = [group_col] + agg_keys

        # ---- 聚合 ----
        ohlc_agg = {
            "open": "first", "high": "max", "low": "min",
            "close": "last", "vol": "sum", "amount": "sum",
        }
        ohlc_agg = {k: v for k, v in ohlc_agg.items() if k in work.columns}
        # 其他数值列：取最后一行（避免聚合丢失用户自定义字段）
        extra_cols = [c for c in work.columns if c not in ohlc_agg
                      and c not in agg_keys and c not in ("_tod", "_date", "_session_idx", "_bar_idx", "_bar_key", time_col)]
        extra_agg = {c: "last" for c in extra_cols}

        result = work.groupby(agg_keys, dropna=False).agg({**ohlc_agg, **extra_agg}).reset_index()

        # ---- 还原时间列 ----
        if mode == "session":
            # 把 (_date, _session_idx, _bar_idx) → datetime
            def _to_dt(row):
                s = sessions[int(row["_session_idx"])][0]
                t = _bar_start_time(s, int(row["_bar_idx"]), minutes)
                return datetime.combine(row["_date"].item() if hasattr(row["_date"], "item") else row["_date"], t)
            result[time_col] = result.apply(_to_dt, axis=1)
        else:
            result.rename(columns={"_bar_key": time_col}, inplace=True)

        # ---- 丢弃未完成 bar ----
        if drop_incomplete:
            # 统计每根 bar 内 1min 根数
            cnt = work.groupby(agg_keys).size().reset_index(name="_cnt")
            result = result.merge(cnt, on=agg_keys, how="left")
            result = result[result["_cnt"] >= minutes].copy()
            result.drop(columns=["_cnt"], inplace=True)

        # ---- 清理辅助列 ----
        for c in ("_date", "_tod", "_session_idx", "_bar_idx", "_bar_key"):
            if c in result.columns:
                result.drop(columns=[c], inplace=True)

        # ---- 排序 ----
        sort_keys = ([group_col, time_col] if group_col and group_col in result.columns else [time_col])
        result.sort_values(by=sort_keys, inplace=True, ignore_index=True)

        return result
