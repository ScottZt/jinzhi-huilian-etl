"""股票列表节点 — 获取 A 股股票列表，支持多种过滤条件。

输出列：code, name, market, industry, is_st
可与 source_fetch 节点串联：股票列表 → 数据拉取。
"""

import logging
import pandas as pd

from app.core.workflow_engine import BaseNode


logger = logging.getLogger("StockListNode")


class StockListNode(BaseNode):
    node_type = "stock_list"
    display_name = "股票列表"
    category = "数据接入"
    params_schema = {
        "market": {
            "type": "select",
            "label": "市场",
            "options": [
                {"value": "all", "label": "全部市场"},
                {"value": "sh", "label": "SH - 上交所"},
                {"value": "sz", "label": "SZ - 深交所"},
                {"value": "bj", "label": "BJ - 北交所"},
            ],
            "default": "all",
        },
        "industry": {
            "type": "select",
            "label": "行业(留空=全部)",
            "options": [
                {"value": "", "label": "全部行业"},
                {"value": "银行", "label": "银行"},
                {"value": "证券", "label": "证券"},
                {"value": "保险", "label": "保险"},
                {"value": "多元金融", "label": "多元金融"},
                {"value": "房地产", "label": "房地产"},
                {"value": "建筑装饰", "label": "建筑装饰"},
                {"value": "建筑材料", "label": "建筑材料"},
                {"value": "钢铁", "label": "钢铁"},
                {"value": "有色金属", "label": "有色金属"},
                {"value": "基础化工", "label": "基础化工"},
                {"value": "煤炭", "label": "煤炭"},
                {"value": "石油石化", "label": "石油石化"},
                {"value": "电力设备", "label": "电力设备"},
                {"value": "机械设备", "label": "机械设备"},
                {"value": "国防军工", "label": "国防军工"},
                {"value": "汽车", "label": "汽车"},
                {"value": "家用电器", "label": "家用电器"},
                {"value": "食品饮料", "label": "食品饮料"},
                {"value": "医药生物", "label": "医药生物"},
                {"value": "纺织服饰", "label": "纺织服饰"},
                {"value": "轻工制造", "label": "轻工制造"},
                {"value": "商贸零售", "label": "商贸零售"},
                {"value": "社会服务", "label": "社会服务"},
                {"value": "农林牧渔", "label": "农林牧渔"},
                {"value": "交通运输", "label": "交通运输"},
                {"value": "公用事业", "label": "公用事业"},
                {"value": "环保", "label": "环保"},
                {"value": "美容护理", "label": "美容护理"},
                {"value": "计算机", "label": "计算机"},
                {"value": "通信", "label": "通信"},
                {"value": "传媒", "label": "传媒"},
                {"value": "电子", "label": "电子"},
                {"value": "综合", "label": "综合"},
            ],
            "default": "",
        },
        "exclude_st": {
            "type": "checkbox",
            "label": "排除ST股",
            "default": True,
        },
        "keyword": {
            "type": "text",
            "label": "关键词过滤",
            "default": "",
            "placeholder": "股票名称或代码包含的关键词",
        },
        "limit": {
            "type": "number",
            "label": "最大返回数量",
            "default": 5000,
        },
        "data_source": {
            "type": "select",
            "label": "数据源",
            "options": [
                {"value": "akshare", "label": "AkShare (免费)"},
                {"value": "tushare", "label": "Tushare (需凭证)"},
            ],
            "default": "akshare",
        },
    }

    def process(self, df: pd.DataFrame, params: dict) -> pd.DataFrame:
        market = str(params.get("market", "all")).strip()
        industry_filter = str(params.get("industry", "")).strip()
        exclude_st = params.get("exclude_st", True)
        keyword = str(params.get("keyword", "")).strip()
        limit = int(params.get("limit", 5000) or 5000)
        data_source = str(params.get("data_source", "akshare")).strip()

        print(f"\n[股票列表] 开始处理，参数:")
        print(f"  - data_source: {data_source}")
        print(f"  - market: {market}")
        print(f"  - industry: {industry_filter}")
        print(f"  - exclude_st: {exclude_st}")
        print(f"  - keyword: {keyword}")
        print(f"  - limit: {limit}")

        # 获取股票列表
        if data_source == "akshare":
            result = self._fetch_from_akshare()
        elif data_source == "tushare":
            result = self._fetch_from_tushare()
        else:
            raise ValueError(f"不支持的数据源: {data_source}")

        print(f"[股票列表] 原始数据: {len(result)} 行")

        if result.empty:
            error_msg = f"[股票列表] 使用 {data_source} 未获取到任何股票数据，请检查网络连接或更换数据源"
            logger.warning(error_msg)
            raise RuntimeError(error_msg)

        # 市场过滤
        if market and market != "all" and "market" in result.columns:
            market_map = {"sh": "SH", "sz": "SZ", "bj": "BJ"}
            result = result[result["market"].str.upper() == market_map.get(market, market.upper())]
            print(f"[股票列表] 市场过滤后: {len(result)} 行")

        # 行业过滤（支持单个行业或逗号分隔的多个行业）
        if industry_filter and "industry" in result.columns:
            # 行业名称映射：申万行业分类 -> Tushare 行业分类
            industry_mapping = {
                "电力设备": ["电气设备", "电力设备"],
                "计算机": ["计算机", "软件服务"],
                "电子": ["电子元器件", "元器件", "电子"],
                "医药生物": ["医药生物", "生物制药", "医疗器械", "化学制药", "中药"],
                "食品饮料": ["食品饮料", "食品", "饮料"],
                "银行": ["银行"],
                "证券": ["证券", "多元金融"],
                "保险": ["保险"],
                "房地产": ["房地产", "地产"],
                "汽车": ["汽车", "汽车配件"],
                "机械设备": ["机械设备", "专用机械", "通用机械"],
                "化工": ["基础化工", "化工", "化学制品", "化学原料"],
                "有色金属": ["有色金属"],
                "钢铁": ["钢铁"],
                "煤炭": ["煤炭"],
                "石油石化": ["石油石化", "石油", "石化"],
                "建筑材料": ["建筑材料", "建材"],
                "建筑装饰": ["建筑装饰", "建筑"],
                "交通运输": ["交通运输", "物流"],
                "公用事业": ["公用事业", "电力", "燃气", "水务"],
                "环保": ["环保"],
                "农林牧渔": ["农林牧渔", "农业", "林业", "畜牧业", "渔业"],
                "纺织服饰": ["纺织服饰", "纺织服装", "服装"],
                "轻工制造": ["轻工制造", "轻工"],
                "商贸零售": ["商贸零售", "商业", "零售"],
                "社会服务": ["社会服务", "旅游", "酒店"],
                "美容护理": ["美容护理", "化妆品"],
                "通信": ["通信"],
                "传媒": ["传媒", "影视", "游戏"],
                "家用电器": ["家用电器", "家电"],
                "国防军工": ["国防军工", "军工", "航天装备"],
            }

            # 支持逗号分隔的多个行业
            industries = [i.strip() for i in industry_filter.split(",") if i.strip()]
            if industries:
                # 扩展行业列表（包括映射后的名称）
                expanded_industries = []
                for ind in industries:
                    if ind in industry_mapping:
                        expanded_industries.extend(industry_mapping[ind])
                    else:
                        expanded_industries.append(ind)

                pattern = "|".join(expanded_industries)
                result = result[result["industry"].str.contains(pattern, na=False)]
                print(f"[股票列表] 行业过滤后: {len(result)} 行 (行业: {pattern})")

        # 排除 ST 股
        if exclude_st and "name" in result.columns:
            before_count = len(result)
            result = result[~result["name"].str.contains("ST", case=False, na=False)]
            print(f"[股票列表] 排除ST后: {len(result)} 行 (排除了 {before_count - len(result)} 只)")

        # 关键词过滤
        if keyword and "name" in result.columns:
            mask = (
                result["name"].str.contains(keyword, case=False, na=False)
                | result["code"].str.contains(keyword, case=False, na=False)
            )
            result = result[mask]
            print(f"[股票列表] 关键词过滤后: {len(result)} 行")

        # 限制数量
        result = result.head(limit)

        # 确保必要列存在
        for col in ["code", "name", "market", "industry", "is_st"]:
            if col not in result.columns:
                result[col] = ""

        result = result[["code", "name", "market", "industry", "is_st"]].reset_index(drop=True)
        print(f"[股票列表] 最终结果: {len(result)} 行")
        logger.info(f"[股票列表] 获取到 {len(result)} 只股票")
        return result

    def _fetch_from_akshare(self) -> pd.DataFrame:
        """从 AkShare 获取 A 股股票列表，带重试机制。"""
        import time

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                import akshare as ak
                df = ak.stock_zh_a_spot_em()
                if df is None or df.empty:
                    return pd.DataFrame()

                # 标准化列名
                result = pd.DataFrame()
                result["code"] = df.get("代码", pd.Series(dtype=str)).astype(str)
                result["name"] = df.get("名称", pd.Series(dtype=str)).astype(str)

                # 根据代码判断市场
                def get_market(code):
                    code = str(code)
                    if code.startswith("6"):
                        return "SH"
                    elif code.startswith("0") or code.startswith("3"):
                        return "SZ"
                    elif code.startswith("4") or code.startswith("8"):
                        return "BJ"
                    return ""

                result["market"] = result["code"].apply(get_market)

                # 行业信息（AkShare 实时行情接口可能没有行业字段，需要额外获取）
                try:
                    industry_df = ak.stock_board_industry_name_em()
                    # 这里简化处理，实际可以通过 stock_individual_info_em 获取个股行业
                    # 但为了性能，暂时留空
                    result["industry"] = ""
                except Exception:
                    result["industry"] = ""

                # 判断是否 ST
                result["is_st"] = result["name"].str.contains("ST", case=False, na=False)

                return result
            except Exception as e:
                last_error = e
                logger.warning(f"[股票列表] AkShare 第 {attempt + 1} 次尝试失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # 递增等待时间
                    continue

        # 所有重试都失败
        error_msg = f"AkShare 获取股票列表失败（已重试 {max_retries} 次）: {last_error}"
        logger.error(f"[股票列表] {error_msg}")
        raise RuntimeError(error_msg)

    def _fetch_from_tushare(self) -> pd.DataFrame:
        """从 Tushare 获取 A 股股票列表。"""
        try:
            import tushare as ts
            from app.persistence import sqlite_repo

            # 查找 tushare 凭证（支持 tushare_token 类型）
            creds = sqlite_repo.list_credentials()
            print(f"\n[DEBUG] 查找到 {len(creds)} 个凭证")
            for c in creds:
                print(f"  - 凭证: name={c.get('name')}, type={c.get('type')}")

            tushare_cred = None
            for c in creds:
                cred_type = c.get("type", "")
                # 支持 tushare_token 和 tushare 两种类型名
                if cred_type in ("tushare_token", "tushare"):
                    tushare_cred = c
                    print(f"[DEBUG] 找到 Tushare 凭证: {c.get('name')}")
                    break

            if not tushare_cred:
                raise RuntimeError(
                    "未找到 Tushare 凭证，请先在「凭证管理」中创建「Tushare Token」类型的凭证"
                )

            # 解密凭证
            from app.core.credential_manager import decrypt_credential
            raw_cfg = tushare_cred.get("config", {})
            if isinstance(raw_cfg, dict) and "_encrypted" in raw_cfg:
                cfg = decrypt_credential(raw_cfg["_encrypted"])
            else:
                cfg = raw_cfg
            token = cfg.get("token", "")
            print(f"[DEBUG] Token 长度: {len(token)}")

            if not token:
                raise RuntimeError("Tushare token 为空，请检查凭证配置")

            ts.set_token(token)
            pro = ts.pro_api()

            # 获取股票列表
            print("[DEBUG] 调用 Tushare stock_basic API...")
            df = pro.stock_basic(exchange="", list_status="L")
            print(f"[DEBUG] Tushare 返回: {type(df)}, 行数: {len(df) if df is not None else 0}")

            if df is None or df.empty:
                return pd.DataFrame()

            result = pd.DataFrame()
            result["code"] = df.get("symbol", df.get("ts_code", pd.Series(dtype=str))).astype(str)
            result["name"] = df.get("name", pd.Series(dtype=str)).astype(str)

            # 市场
            def get_market(code):
                code = str(code)
                if code.startswith("6"):
                    return "SH"
                elif code.startswith("0") or code.startswith("3"):
                    return "SZ"
                elif code.startswith("4") or code.startswith("8"):
                    return "BJ"
                return ""

            result["market"] = result["code"].apply(get_market)

            # 行业
            result["industry"] = df.get("industry", pd.Series(dtype=str)).astype(str)

            # ST
            result["is_st"] = result["name"].str.contains("ST", case=False, na=False)

            print(f"[DEBUG] 处理后数据: {len(result)} 行, 列: {list(result.columns)}")
            print(f"[DEBUG] 市场分布: {result['market'].value_counts().to_dict()}")
            print(f"[DEBUG] 行业数量: {result['industry'].nunique()}")
            print(f"[DEBUG] 行业示例: {result['industry'].value_counts().head(5).to_dict()}")

            return result
        except RuntimeError:
            raise
        except Exception as e:
            error_msg = f"Tushare 获取股票列表失败: {e}"
            logger.error(f"[股票列表] {error_msg}")
            raise RuntimeError(error_msg)
