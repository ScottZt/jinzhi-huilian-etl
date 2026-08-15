"""数据聚合节点 — 对数据进行 sum/avg/count/min/max 等聚合操作。"""
import logging
import pandas as pd
from typing import Optional
from app.core.workflow_engine import BaseNode

logger = logging.getLogger(__name__)


class AggregationNode(BaseNode):
    node_type = "aggregation"
    display_name = "数据聚合"
    category = "数据处理"
    params_schema = {
        "group_by": {
            "type": "text",
            "label": "分组字段",
            "default": "",
            "placeholder": "按哪些字段分组（逗号分隔），留空=全局聚合"
        },
        "aggregations": {
            "type": "textarea",
            "label": "聚合规则",
            "default": "",
            "placeholder": "格式：新列名=源列:聚合函数\n如：total_vol=vol:sum,avg_price=price:mean,record_count=code:count"
        },
        "preset": {
            "type": "select",
            "label": "预设模板",
            "options": ["custom", "ohlcv", "count_only", "all_stats"],
            "default": "custom",
            "placeholder": "选择预设的聚合模板"
        },
        "source_column": {
            "type": "text",
            "label": "统计字段",
            "default": "close",
            "placeholder": "预设模板使用的字段"
        },
        "reset_index": {
            "type": "checkbox",
            "label": "重置索引",
            "default": True
        },
    }

    def process(self, df: pd.DataFrame, params: dict, context: Optional[dict] = None) -> pd.DataFrame:
        """
        对数据进行聚合操作。
        """
        if df.empty:
            return df

        group_by_str = params.get("group_by", "").strip()
        aggregations_str = params.get("aggregations", "").strip()
        preset = params.get("preset", "custom")
        source_column = params.get("source_column", "close").strip()
        reset_index = params.get("reset_index", True)

        # 解析分组字段
        group_cols = [c.strip() for c in group_by_str.split(",") if c.strip()] if group_by_str else []

        # 验证分组字段存在
        if group_cols:
            missing = [c for c in group_cols if c not in df.columns]
            if missing:
                logger.warning("AggregationNode: 分组字段不存在: %s", missing)
                return df

        # 解析聚合规则
        agg_dict = self._parse_aggregations(aggregations_str, preset, source_column, df.columns)
        if not agg_dict:
            logger.warning("AggregationNode: 聚合规则为空")
            return df

        try:
            # 执行聚合
            if group_cols:
                result = df.groupby(group_cols).agg(agg_dict)
            else:
                # 全局聚合
                result = df.agg(agg_dict)
                # 全局聚合返回的是 Series，需要转为 DataFrame
                if isinstance(result, pd.Series):
                    result = result.to_frame().T
                elif isinstance(result, dict):
                    result = pd.DataFrame([result])

            # 扁平化列名（如果有多级列）
            if isinstance(result.columns, pd.MultiIndex):
                result.columns = ['_'.join(col).strip('_') for col in result.columns]

            # 重置索引
            if reset_index:
                result = result.reset_index()

            logger.info("AggregationNode: 聚合完成，输出 %d 行", len(result))
            return result

        except Exception as e:
            logger.error("AggregationNode: 聚合失败: %s", e)
            return df

    def _parse_aggregations(self, agg_str: str, preset: str, source_column: str, columns) -> dict:
        """
        解析聚合规则。

        格式：新列名=源列:聚合函数,新列名2=源列2:聚合函数2
        例如：total_vol=vol:sum,avg_price=price:mean

        支持的聚合函数：sum, mean/avg, count, min, max, std, var, first, last, nunique
        """
        # 预设模板
        if preset == "ohlcv" and source_column in columns:
            # OHLCV 标准聚合
            agg_dict = {}
            if 'open' in columns:
                agg_dict['open'] = 'first'
            if 'high' in columns:
                agg_dict['high'] = 'max'
            if 'low' in columns:
                agg_dict['low'] = 'min'
            if 'close' in columns:
                agg_dict['close'] = 'last'
            if 'vol' in columns or 'volume' in columns:
                vol_col = 'vol' if 'vol' in columns else 'volume'
                agg_dict[vol_col] = 'sum'
            return agg_dict

        elif preset == "count_only" and source_column in columns:
            return {source_column: 'count'}

        elif preset == "all_stats" and source_column in columns:
            return {
                f'{source_column}_sum': (source_column, 'sum'),
                f'{source_column}_mean': (source_column, 'mean'),
                f'{source_column}_min': (source_column, 'min'),
                f'{source_column}_max': (source_column, 'max'),
                f'{source_column}_std': (source_column, 'std'),
                f'{source_column}_count': (source_column, 'count'),
            }

        # 自定义解析
        if not agg_str:
            return {}

        agg_dict = {}
        # 聚合函数映射
        func_map = {
            'sum': 'sum',
            'mean': 'mean', 'avg': 'mean',
            'count': 'count',
            'min': 'min',
            'max': 'max',
            'std': 'std',
            'var': 'var',
            'first': 'first',
            'last': 'last',
            'nunique': 'nunique',
        }

        for rule in agg_str.split(","):
            rule = rule.strip()
            if not rule or "=" not in rule or ":" not in rule:
                continue

            try:
                # 格式：新列名=源列:聚合函数
                new_col, rest = rule.split("=", 1)
                src_col, func_name = rest.split(":", 1)
                new_col = new_col.strip()
                src_col = src_col.strip()
                func_name = func_name.strip().lower()

                if src_col not in columns:
                    logger.warning("AggregationNode: 字段 '%s' 不存在，跳过", src_col)
                    continue

                if func_name not in func_map:
                    logger.warning("AggregationNode: 未知聚合函数 '%s'，跳过", func_name)
                    continue

                # 使用 pd.NamedAgg 或字典形式
                agg_dict[new_col] = pd.NamedAgg(column=src_col, aggfunc=func_map[func_name])

            except Exception as e:
                logger.warning("AggregationNode: 解析规则 '%s' 失败: %s", rule, e)

        return agg_dict
