from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uuid
import os
import json
import re
from html import unescape

from app.persistence import sqlite_repo
from app.core.credential_manager import encrypt_credential, decrypt_credential
from app.core import license_manager as lm

router = APIRouter()

def _safe_int_env(name: str, default: int) -> int:
    """安全读取整型环境变量，避免非法值导致服务启动失败。"""
    raw = str(os.getenv(name, str(default))).strip()
    try:
        val = int(raw)
        return val if val > 0 else default
    except Exception:
        return default


# 云端体验模式每设备调用上限（默认 10 次，可由环境变量覆盖）。
_CLOUD_DEMO_MAX_CALLS = _safe_int_env("QS_CLOUD_DEMO_MAX_CALLS", 10)


class LLMConfigCreate(BaseModel):
    name: str = "default"
    provider: str = "cloud_demo"
    base_url: str = "https://api.siliconflow.cn/v1"
    api_key: str = ""
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    system_prompt: str = ""
    stream_mode: str = "normal"  # normal | sse
    enabled: int = 1


class AssistantGuideRequest(BaseModel):
    scene: str  # credential | datasource | connection | workflow
    goal: str = ""
    current_config: Dict[str, Any] = {}
    last_error: str = ""
    mode: str = "wizard"  # wizard | troubleshoot


class AssistantEventCreate(BaseModel):
    event_name: str
    scene: str
    payload: Dict[str, Any] = {}


class ApiTemplateFromUrlRequest(BaseModel):
    doc_url: str
    source_hint: str = "tushare"
    cat_hint: str = "market"


def _safe_json_loads(text: str):
    """安全解析 JSON 字符串，失败返回 None。"""
    try:
        return json.loads(text)
    except Exception:
        return None


def _build_datasource_diagnostic_plan(current_config: Dict[str, Any], last_error: str) -> Dict[str, Any]:
    """针对数据源场景生成可执行诊断结果（规则版，优先可落地修复动作）。"""
    cfg = current_config or {}
    err = (last_error or "").lower()
    source_type = str(cfg.get("type", "http") or "http").lower()
    base_url = str(cfg.get("base_url", "") or "").strip()
    method = str(cfg.get("method", "") or "").upper()
    request_template_raw = str(cfg.get("request_template", "") or "").strip()
    preview_codes = str(cfg.get("preview_codes", "") or "").strip()

    diagnosis: List[str] = []
    quick_actions: List[Dict[str, Any]] = []
    steps = [
        {"title": "先修必填参数", "detail": "优先修 base_url、method、request_template 三个高频失败点。"},
        {"title": "执行一次重测", "detail": "应用修复动作后立即重测，确认连通性是否恢复。"},
        {"title": "再做样例预览", "detail": "重测通过后预览样例数据，确认字段结构再保存。"},
    ]
    checks = ["base_url 非空且协议正确", "request_template 为合法 JSON", "重测返回 success=true"]

    if source_type == "http":
        # 1) base_url 缺失/格式错误
        if not base_url:
            diagnosis.append("缺少 base_url：当前数据源没有配置 API 基础地址。")
            quick_actions.append({"label": "填入 Tushare 地址", "selector": "#ks-cfg-base_url", "value": "http://api.tushare.pro"})
        elif not (base_url.startswith("http://") or base_url.startswith("https://")):
            diagnosis.append("base_url 协议异常：应以 http:// 或 https:// 开头。")
            fixed_url = f"https://{base_url.lstrip('/')}"
            quick_actions.append({"label": "修正 base_url 协议", "selector": "#ks-cfg-base_url", "value": fixed_url})

        # 2) method 缺失
        if method not in ("GET", "POST"):
            diagnosis.append("HTTP 方法未设置：建议先用 POST（量化 API 常见）。")
            quick_actions.append({"label": "切换为 POST 请求", "selector": "#ks-cfg-method", "value": "POST"})

        # 3) request_template 问题
        if not request_template_raw:
            diagnosis.append("request_template 为空：无法构造请求参数。")
            quick_actions.append({
                "label": "写入默认请求模板",
                "selector": "#ks-cfg-request_template",
                # Tushare Pro（doc_id=40）默认模板：使用 trade_cal 示例结构，便于通用接口替换。
                "value": '{"api_name":"trade_cal","token":"{TUSHARE_TOKEN}","params":{"exchange":"","start_date":"{start_time}","end_date":"{end_time}","is_open":"0"},"fields":"exchange,cal_date,is_open,pretrade_date"}',
            })
        elif _safe_json_loads(request_template_raw) is None:
            diagnosis.append("request_template 不是合法 JSON：请修复引号和括号。")

        # 4) 预览标的建议
        if not preview_codes:
            diagnosis.append("预览代码为空：建议先用 000001 验证链路。")
            quick_actions.append({"label": "写入默认预览代码", "selector": "#ks-cfg-preview_codes", "value": "000001,600000"})

        # 5) 基于错误文本补充精准定位
        if "401" in err or "403" in err or "unauthorized" in err or "token" in err:
            diagnosis.append("认证失败：当前请求可能未带有效凭证（Token/Authorization）。")
            checks.append("请求头中含 Authorization 或已绑定可用凭证")
        if "timeout" in err or "timed out" in err:
            diagnosis.append("请求超时：优先检查 base_url 可达性，再检查网络代理设置。")
        if "name or service not known" in err or "nodename" in err or "dns" in err:
            diagnosis.append("域名解析失败：请检查 base_url 域名是否正确。")
        if "invalid url" in err:
            diagnosis.append("URL 非法：base_url 可能包含空格或缺少协议头。")
    else:
        # 非 HTTP 类型先给最小可执行建议，避免误导。
        diagnosis.append(f"当前数据源类型为 {source_type}，请优先检查该类型必填参数是否完整。")

    # 若未识别到明确问题，也给出可执行默认动作，避免再次“空建议”体验。
    if not diagnosis:
        diagnosis.append("未识别到单一故障点：建议先执行重测并查看最新错误，再做定向修复。")
        quick_actions.append({"label": "写入默认预览代码", "selector": "#ks-cfg-preview_codes", "value": "000001,600000"})

    # 闭环动作：直接在助手里触发重测/预览，减少来回切换。
    quick_actions.append({"label": "应用后立即重测", "action": "retest_datasource"})
    quick_actions.append({"label": "重测后做样例预览", "action": "preview_datasource"})

    return {
        "summary": "已根据当前数据源配置与错误信息生成定向修复方案，先修必填再重测。",
        "steps": steps,
        "checks": checks,
        "quick_actions": quick_actions,
        "diagnosis": diagnosis,
    }


def _build_local_assistant_plan(body: AssistantGuideRequest) -> Dict[str, Any]:
    """基于场景输出可直接执行的交互引导计划（本地规则版）。"""
    scene = (body.scene or "").strip().lower()
    goal = (body.goal or "").strip()
    last_error = (body.last_error or "").strip()
    current_config = body.current_config or {}

    # 默认回退建议，避免场景不匹配时返回空结构。
    result: Dict[str, Any] = {
        "scene": scene or "generic",
        "summary": "按“先最小可用、再测试验证、最后保存复用”的顺序完成配置。",
        "steps": [
            {"title": "明确目标", "detail": "先确认你要拉取/写入的数据类型和时间范围。"},
            {"title": "填写必填项", "detail": "只填必填字段，非必要参数先用默认值。"},
            {"title": "立即测试", "detail": "每次改动后先测试连通性，再继续下一步。"},
        ],
        "checks": ["必填项不为空", "测试接口返回成功", "保存后可再次复测"],
        "quick_actions": [],
    }

    # 凭证场景：优先保证认证信息可用。
    if scene == "credential":
        cred_type = str(current_config.get("type", "")).lower()
        result.update({
            "summary": "先完成凭证最小配置，再用一次轻量请求验证 Token/账号是否有效。",
            "steps": [
                {"title": "选择凭证类型", "detail": "按数据源协议选择 Tushare、Bearer、BasicAuth 或 APIKey。"},
                {"title": "填写必填参数", "detail": "仅填写 token/用户名密码/base_url 等必要项。"},
                {"title": "执行连通测试", "detail": "点击“测试”后根据错误类型修正参数。"},
            ],
            "checks": ["token 或账号密码已填写", "base_url 格式正确", "测试返回 success=true"],
            "quick_actions": [
                {"label": "填入 Tushare 默认地址", "selector": "#cred-cfg-base_url", "value": "http://api.tushare.pro"},
                {"label": "切换到凭证管理页", "action": "navigate_credentials"},
            ],
        })
        if cred_type == "tushare_token":
            result["checks"].append("Token 长度与格式符合 Tushare 要求")

    # 数据源场景：聚焦 base_url、headers、request_template 三件套。
    elif scene == "datasource":
        result.update(_build_datasource_diagnostic_plan(current_config, last_error))

    # 连接场景：重点保障数据库/文件连接可测可存。
    elif scene == "connection":
        result.update({
            "summary": "先使用默认网络参数建连，再按测试结果微调 host/port/认证信息。",
            "steps": [
                {"title": "选择连接类型", "detail": "按目标选择 mysql/postgresql/duckdb/clickhouse 或文件型连接。"},
                {"title": "填写最小必填参数", "detail": "数据库至少填 host、port、user、password、database。"},
                {"title": "执行连接测试", "detail": "成功后再保存；失败时按错误信息逐项排查。"},
            ],
            "checks": ["连接名称已填写", "关键参数完整", "测试返回 success=true"],
            "quick_actions": [
                {"label": "填入默认主机", "selector": "#conn-cfg-host", "value": "localhost"},
                {"label": "填入 MySQL 默认端口", "selector": "#conn-cfg-port", "value": "3306"},
            ],
        })

    # 工作流场景：强调模板复用和最短链路。
    elif scene == "workflow":
        result.update({
            "summary": "先复用模板搭骨架，再做最小参数修改并预览结果。",
            "steps": [
                {"title": "选择最近场景模板", "detail": "优先使用“日线清洗/分钟转日线/均线生成”模板。"},
                {"title": "只改关键参数", "detail": "先改时间字段、目标周期、指标窗口，其他保持默认。"},
                {"title": "单节点试跑", "detail": "先预览中间结果，再全流程保存。"},
            ],
            "checks": ["节点至少包含输入与输出链路", "预览返回列结构正确", "保存后可重复加载"],
            "quick_actions": [
                {"label": "打开工作流编辑器", "action": "open_workflow_editor"},
                {"label": "切换到工作流页", "action": "navigate_workflows"},
            ],
        })

    # 故障模式下附加定位建议，减少来回试错。
    if body.mode == "troubleshoot" and last_error:
        result["troubleshoot"] = [
            "先检查网络连通性与 DNS 解析是否正常。",
            "确认请求地址、认证信息和请求方法是否匹配。",
            f"最近错误信息：{last_error}",
        ]

    return result


def _is_local_free_provider(cfg: Dict[str, Any]) -> bool:
    """识别无需 API Key 的本地免费模型场景（如 Ollama）。"""
    provider = str(cfg.get("provider", "")).strip().lower()
    base_url = str(cfg.get("base_url", "")).strip().lower()
    if provider == "ollama":
        return True
    # 兼容用户将 Ollama 以 custom 方式填写的情况。
    return ("127.0.0.1:11434" in base_url) or ("localhost:11434" in base_url)


def _is_cloud_demo_provider(cfg: Dict[str, Any]) -> bool:
    """识别云端免费体验通道。"""
    provider = str(cfg.get("provider", "")).strip().lower()
    return provider == "cloud_demo"


def _resolve_effective_api_key(cfg: Dict[str, Any]) -> str:
    """解析真实可用 API Key：优先用户自填，其次云端体验环境变量。"""
    direct_key = str(cfg.get("api_key", "") or "").strip()
    if direct_key:
        return direct_key
    # 云端体验通道允许走平台预置 Key，避免新用户首配门槛。
    if _is_cloud_demo_provider(cfg):
        return str(os.getenv("QS_ETL_DEMO_API_KEY", "")).strip()
    return ""


def _is_using_shared_demo_key(cfg: Dict[str, Any]) -> bool:
    """是否正在使用平台托管的体验 Key（而非用户自填 Key）。"""
    if not _is_cloud_demo_provider(cfg):
        return False
    return not bool(str(cfg.get("api_key", "") or "").strip())


def _cloud_demo_usage_key() -> str:
    """构造按设备统计的体验调用计数键。"""
    machine_code = lm.get_machine_code()
    return f"_cloud_demo_calls_{machine_code}"


def _get_cloud_demo_usage() -> int:
    """读取当前设备累计体验调用次数。"""
    raw = sqlite_repo.get_metadata(_cloud_demo_usage_key()) or "0"
    try:
        return int(raw)
    except Exception:
        return 0


def _get_cloud_demo_remaining() -> int:
    """计算当前设备剩余体验次数。"""
    used = _get_cloud_demo_usage()
    return max(0, _CLOUD_DEMO_MAX_CALLS - used)


def _consume_cloud_demo_quota_if_needed(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """按需扣减云端体验额度；非体验通道或自带 Key 不扣减。"""
    if not _is_using_shared_demo_key(cfg):
        return {"ok": True, "remaining": -1}
    remaining = _get_cloud_demo_remaining()
    if remaining <= 0:
        return {
            "ok": False,
            "remaining": 0,
            "error": f"云端免费体验额度已用完（每设备最多 {_CLOUD_DEMO_MAX_CALLS} 次）。请填写你自己的 API Key 或升级服务。",
        }
    # 先扣减后调用，避免并发情况下透支。
    sqlite_repo.save_metadata(_cloud_demo_usage_key(), str(_get_cloud_demo_usage() + 1))
    return {"ok": True, "remaining": max(0, remaining - 1)}


def _build_llm_headers(cfg: Dict[str, Any]) -> Dict[str, str]:
    """按模型类型构建请求头，本地免费模型不要求 Bearer Token。"""
    headers = {"Content-Type": "application/json"}
    api_key = _resolve_effective_api_key(cfg)
    # 本地模型可无 key；云端模型必须带 Authorization。
    if (not _is_local_free_provider(cfg)) and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _extract_doc_text_from_url(doc_url: str) -> str:
    """抓取文档链接并提取可供 LLM 阅读的正文文本。"""
    url = str(doc_url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("文档链接必须以 http:// 或 https:// 开头")
    try:
        import requests
    except Exception:
        raise RuntimeError("运行环境缺少 requests 依赖，无法抓取网页文档")

    # 使用轻量浏览器 UA，减少部分站点对默认客户端的拦截概率。
    headers = {"User-Agent": "Mozilla/5.0 (compatible; QuantSync-ETL/1.0; +https://localhost)"}
    resp = requests.get(url, headers=headers, timeout=(8, 25))
    if resp.status_code >= 400:
        raise RuntimeError(f"读取文档失败：HTTP {resp.status_code}")

    content_type = str(resp.headers.get("Content-Type", "")).lower()
    raw = resp.text or ""
    if "application/json" in content_type:
        # JSON 文档直接返回，保留结构信息给模型解析字段。
        return raw[:15000]

    # 对 HTML 做基础净化：移除 script/style，再去标签并压缩空白。
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:15000]


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """从 LLM 文本中提取首个 JSON 对象，兼容 ```json 代码块。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    # 优先处理 markdown 代码块返回格式。
    block = re.search(r"```json\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
    if block:
        raw = block.group(1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    # 兜底：截取首个大括号包裹内容尝试解析。
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start:end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _normalize_tushare_req_example(req_example_obj: Dict[str, Any], api_name: str, fields: str) -> Dict[str, Any]:
    """归一化 Tushare 请求体：统一为 api_name + token + params + fields 四段式。"""
    req = dict(req_example_obj or {})
    # Tushare 通用调用方式：接口名优先取文档解析值，缺失时回退 trade_cal（doc_id=40 示例）。
    req["api_name"] = str(req.get("api_name") or api_name or "trade_cal").strip()
    # token 必须在请求体中传递，不放在 headers。
    req["token"] = str(req.get("token") or "{TUSHARE_TOKEN}").strip()

    raw_params = req.get("params", {})
    if not isinstance(raw_params, dict):
        raw_params = {}
    # 兼容旧模板的通用字段命名，统一映射到 Tushare 常用参数。
    if "codes" in raw_params and "ts_code" not in raw_params:
        raw_params["ts_code"] = raw_params.get("codes")
    if "start" in raw_params and "start_date" not in raw_params:
        raw_params["start_date"] = raw_params.get("start")
    if "end" in raw_params and "end_date" not in raw_params:
        raw_params["end_date"] = raw_params.get("end")
    # 补齐最小可用时间参数占位符，便于系统自动替换日期区间。
    # 对于 doc_id=40 的 trade_cal 示例，不强制 ts_code，默认给 exchange/is_open。
    if req["api_name"] != "trade_cal":
        raw_params.setdefault("ts_code", "{codes}")
    raw_params.setdefault("exchange", "")
    raw_params.setdefault("start_date", "{start_time}")
    raw_params.setdefault("end_date", "{end_time}")
    raw_params.setdefault("is_open", "0")
    req["params"] = raw_params

    # fields 允许留空；若未给出则使用 doc_id=40 的 trade_cal 字段示例。
    req["fields"] = str(
        req.get("fields")
        or fields
        or "exchange,cal_date,is_open,pretrade_date"
    ).strip()
    return req


def _normalize_template_payload(payload: Dict[str, Any], source_hint: str, cat_hint: str) -> Dict[str, Any]:
    """归一化 AI 抽取结果，保证前端可直接回填到“自定义模板”弹窗。"""
    src_raw = str(payload.get("src") or payload.get("source") or source_hint or "tushare").strip().lower()
    src = src_raw if src_raw in ("tushare", "akshare") else "tushare"
    cat_raw = str(payload.get("cat") or payload.get("category") or cat_hint or "market").strip().lower()
    cat = cat_raw if cat_raw in ("market", "finance", "fund", "index", "flow", "sector") else "market"
    api_name = str(payload.get("apiName") or payload.get("api_name") or "").strip()
    desc = str(payload.get("desc") or payload.get("description") or "AI 生成模板").strip()
    params = str(payload.get("params") or "").strip()
    fields = str(payload.get("fields") or "").strip()
    base_url = str(payload.get("baseUrl") or payload.get("base_url") or "").strip()
    method_raw = str(payload.get("method") or "POST").strip().upper()
    method = method_raw if method_raw in ("GET", "POST") else "POST"

    req_example_obj = payload.get("reqExample", payload.get("req_example"))
    if isinstance(req_example_obj, str):
        try:
            req_example_obj = json.loads(req_example_obj)
        except Exception:
            req_example_obj = {}
    if not isinstance(req_example_obj, dict):
        req_example_obj = {}

    # 若模型未给出 reqExample，则按来源补最小可用模板。
    if not req_example_obj:
        if src == "akshare":
            req_example_obj = {"func": api_name or "custom_api"}
        else:
            req_example_obj = _normalize_tushare_req_example({}, api_name, fields)
    elif src == "tushare":
        # 即使模型返回了 reqExample，也统一做一次 Tushare 结构归一化，降低模板不可用概率。
        req_example_obj = _normalize_tushare_req_example(req_example_obj, api_name, fields)

    # Tushare 板块默认采用官方统一入口和 POST 调用方式。
    # 说明：baseUrl 仅在缺失时补默认值，若用户传入自定义地址则保持不变。
    if src == "tushare" and not base_url:
        base_url = "http://api.tushare.pro"
    if src == "tushare":
        method = "POST"

    return {
        "src": src,
        "cat": cat,
        "apiName": api_name,
        "desc": desc,
        "params": params,
        "fields": fields,
        "baseUrl": base_url,
        "method": method,
        "reqExample": json.dumps(req_example_obj, ensure_ascii=False, indent=2),
    }


def _build_api_template_prompts(doc_url: str, source_hint: str, cat_hint: str, doc_text: str) -> Dict[str, str]:
    """构造“文档转 API 模板”提示词，供普通与 SSE 两种模式复用。"""
    system_prompt = (
        "你是 API 模板抽取助手。请从文档正文中提取可用于 ETL 配置的接口模板，"
        "只输出一个 JSON 对象，不要输出其他说明。"
    )
    tushare_hint = ""
    if str(source_hint or "").strip().lower() == "tushare":
        # 对 Tushare 文档增加硬约束，避免模型输出与实际调用方式不一致。
        tushare_hint = (
            "\nTushare 专用要求：\n"
            "1) method 必须输出 POST。\n"
            "2) baseUrl 默认给出 http://api.tushare.pro，但必须允许用户替换为自定义地址。\n"
            "3) reqExample 必须是 Tushare 通用请求体："
            '{"api_name":"接口名","token":"{TUSHARE_TOKEN}","params":{...},"fields":"..."}。\n'
            "4) token 放在请求体 token 字段，不放在 headers。\n"
            "5) params 优先使用文档里的原生参数名（如 exchange/start_date/end_date/is_open 或 ts_code）。\n"
        )
    user_prompt = (
        f"文档链接: {doc_url}\n"
        f"来源提示: {source_hint}\n"
        f"分类提示: {cat_hint}\n\n"
        "请严格输出以下 JSON 结构（字段名保持一致）:\n"
        "{\n"
        '  "src": "tushare|akshare",\n'
        '  "cat": "market|finance|fund|index|flow|sector",\n'
        '  "apiName": "接口名",\n'
        '  "desc": "接口说明",\n'
        '  "params": "逗号分隔参数列表",\n'
        '  "fields": "逗号分隔返回字段",\n'
        '  "baseUrl": "可选，接口基础地址",\n'
        '  "method": "GET 或 POST",\n'
        '  "reqExample": { "示例请求体对象": true }\n'
        "}\n\n"
        f"{tushare_hint}\n"
        "文档正文（已截断）:\n"
        f"{doc_text}"
    )
    return {"system": system_prompt, "user": user_prompt}


def _build_llm_assistant_advice(body: AssistantGuideRequest, local_plan: Dict[str, Any]) -> str:
    """在本地规则结果之上追加 LLM 文本建议，失败时返回空字符串。"""
    # 读取当前可用模型配置：优先启用项，保证与用户“AI 设置”一致。
    cfg = sqlite_repo.get_active_llm_config()
    if not cfg:
        return ""
    if not cfg.get("enabled"):
        return ""
    if not cfg.get("base_url"):
        return ""
    if (not _is_local_free_provider(cfg)) and (not _resolve_effective_api_key(cfg)):
        return ""

    base_url = cfg["base_url"].rstrip("/")
    model = cfg.get("model", "Qwen/Qwen2.5-7B-Instruct")
    system_prompt = (
        "你是量化 ETL 交互式助手。请基于已有规则建议，补充3-5条可执行、简短、"
        "按优先级排序的操作建议。避免空泛描述，不要输出代码块。"
    )
    user_prompt = (
        f"场景: {body.scene}\n"
        f"模式: {body.mode}\n"
        f"目标: {body.goal}\n"
        f"最近错误: {body.last_error}\n"
        f"当前配置: {body.current_config}\n"
        f"已有规则建议: {local_plan}\n"
        "请输出中文要点列表。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        # 使用 requests 并在函数内导入，避免缺少可选依赖导致服务启动失败。
        import requests
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.2},
            headers=_build_llm_headers(cfg),
            timeout=(8, 25),
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
        return content.strip() if isinstance(content, str) else ""
    except Exception:
        # LLM 增强失败时静默降级，继续返回本地规则结果。
        return ""


@router.get("/")
async def list_all():
    return sqlite_repo.list_ll_configs()


@router.get("/public-config")
async def get_public_config():
    """返回前端可展示的公共配置，不包含任何敏感信息。"""
    # 仅暴露“是否已配置体验通道”的布尔值，不返回任何 key 内容。
    demo_key_ready = bool(str(os.getenv("QS_ETL_DEMO_API_KEY", "")).strip())
    return {
        "siliconflow_invite_url": os.getenv("QS_SILICONFLOW_INVITE_URL", "https://cloud.siliconflow.cn/"),
        "cloud_demo_max_calls": _CLOUD_DEMO_MAX_CALLS,
        "cloud_demo_ready": demo_key_ready,
    }


@router.post("/")
async def create(body: LLMConfigCreate):
    cfg_id = str(uuid.uuid4())
    result = sqlite_repo.save_llm_config({
        "id": cfg_id, "name": body.name, "provider": body.provider,
        "base_url": body.base_url, "api_key": body.api_key,
        "model": body.model, "system_prompt": body.system_prompt, "stream_mode": body.stream_mode,
        "enabled": body.enabled,
    })
    return {"id": cfg_id, **result}


@router.put("/{cfg_id}")
async def update(cfg_id: str, body: LLMConfigCreate):
    result = sqlite_repo.save_llm_config({
        "id": cfg_id, "name": body.name, "provider": body.provider,
        "base_url": body.base_url, "api_key": body.api_key,
        "model": body.model, "system_prompt": body.system_prompt, "stream_mode": body.stream_mode,
        "enabled": body.enabled,
    })
    return result


@router.post("/chat")
async def chat(body: dict):
    """Send a message to the configured LLM."""
    cfg = sqlite_repo.get_llm_config(body.get("config_id", "default"))
    if not cfg:
        return {"error": "请先配置大模型"}
    if not cfg.get("base_url"):
        return {"error": "请先填入 base_url"}
    if (not _is_local_free_provider(cfg)) and (not _resolve_effective_api_key(cfg)):
        # 体验通道未配置时给出可操作提示，避免用户困惑。
        if _is_cloud_demo_provider(cfg):
            return {"error": "当前环境未配置云端免费体验通道，请联系管理员设置 QS_ETL_DEMO_API_KEY，或手动填写 API Key。"}
        return {"error": "请先填入 API Key"}
    # 云端免费体验模式额度控制：每设备最多调用固定次数。
    quota = _consume_cloud_demo_quota_if_needed(cfg)
    if not quota.get("ok"):
        return {"error": quota.get("error"), "remaining_calls": quota.get("remaining", 0)}

    try:
        import requests
    except Exception:
        return {"error": "运行环境缺少 requests 依赖，无法调用云端模型"}
    base_url = cfg["base_url"].rstrip("/")
    model = cfg.get("model", "Qwen/Qwen2.5-7B-Instruct")
    system_prompt = cfg.get("system_prompt", "") or "你是一个量化交易 ETL 系统的技术顾问。"

    messages = [{"role": "system", "content": system_prompt}]
    if body.get("messages"):
        messages.extend(body["messages"])
    else:
        messages.append({"role": "user", "content": body.get("message", "")})

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
            },
            headers=_build_llm_headers(cfg),
            timeout=(10, 60),
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"content": data["choices"][0]["message"]["content"], "remaining_calls": quota.get("remaining", -1)}
        else:
            return {"error": f"LLM 返回错误：HTTP {resp.status_code} - {resp.text[:500]}"}
    except requests.exceptions.Timeout:
        return {"error": "请求超时，请检查网络连接"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/troubleshoot")
async def troubleshoot(body: dict):
    """AI 辅助排查错误。"""
    error = body.get("error", "")
    context = body.get("context", "")
    cfg = sqlite_repo.get_llm_config(body.get("config_id", "default"))
    if not cfg or not cfg.get("base_url"):
        return {"error": "请先配置大模型（设置 base_url）"}
    if (not _is_local_free_provider(cfg)) and (not _resolve_effective_api_key(cfg)):
        if _is_cloud_demo_provider(cfg):
            return {"error": "当前环境未配置云端免费体验通道，请联系管理员设置 QS_ETL_DEMO_API_KEY，或手动填写 API Key。"}
        return {"error": "请先配置大模型（设置 API Key）"}
    # 云端免费体验模式额度控制：每设备最多调用固定次数。
    quota = _consume_cloud_demo_quota_if_needed(cfg)
    if not quota.get("ok"):
        return {"error": quota.get("error"), "remaining_calls": quota.get("remaining", 0)}

    try:
        import requests
    except Exception:
        return {"error": "运行环境缺少 requests 依赖，无法调用云端模型"}
    base_url = cfg["base_url"].rstrip("/")
    model = cfg.get("model", "Qwen/Qwen2.5-7B-Instruct")

    system_prompt = f"""你是一个量化交易 ETL 系统的技术顾问。用户遇到了数据源配置或连接问题。
请分析错误信息，给出排查步骤和解决方案。回答要简洁、有针对性。
"""
    user_msg = f"## 错误信息\n{error}\n\n## 上下文\n{context}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.3},
            headers=_build_llm_headers(cfg),
            timeout=(10, 60),
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"advice": data["choices"][0]["message"]["content"], "remaining_calls": quota.get("remaining", -1)}
        else:
            return {"error": f"LLM 返回错误：HTTP {resp.status_code} - {resp.text[:300]}"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/assistant-guide")
async def assistant_guide(body: AssistantGuideRequest):
    """返回交互式辅助建议：本地规则兜底 + 可选 LLM 增强文本。"""
    result = _build_local_assistant_plan(body)
    # 仅在用户有明确目标或处于排障模式时触发 LLM 增强，减少无效调用。
    should_enhance = body.mode == "troubleshoot" or len((body.goal or "").strip()) >= 8
    if should_enhance:
        advice = _build_llm_assistant_advice(body, result)
        if advice:
            result["llm_advice"] = advice
    return result


@router.post("/api-template-from-url")
async def api_template_from_url(body: ApiTemplateFromUrlRequest):
    """读取网页文档并用 LLM 抽取 API 模板，返回可直接回填的结构化结果。"""
    doc_url = str(body.doc_url or "").strip()
    if not doc_url:
        return {"error": "请先提供文档链接"}

    cfg = sqlite_repo.get_active_llm_config()
    if not cfg:
        return {"error": "请先在 AI 设置中配置并启用模型"}
    if not cfg.get("base_url"):
        return {"error": "请先在 AI 设置中填写 base_url"}
    if (not _is_local_free_provider(cfg)) and (not _resolve_effective_api_key(cfg)):
        if _is_cloud_demo_provider(cfg):
            return {"error": "当前环境未配置云端免费体验通道，请联系管理员设置 QS_ETL_DEMO_API_KEY，或手动填写 API Key。"}
        return {"error": "请先在 AI 设置中配置 API Key"}

    quota = _consume_cloud_demo_quota_if_needed(cfg)
    if not quota.get("ok"):
        return {"error": quota.get("error"), "remaining_calls": quota.get("remaining", 0)}

    try:
        doc_text = _extract_doc_text_from_url(doc_url)
    except Exception as e:
        return {"error": f"读取文档失败: {e}"}

    prompts = _build_api_template_prompts(doc_url, body.source_hint, body.cat_hint, doc_text)

    base_url = str(cfg.get("base_url", "")).rstrip("/")
    model = str(cfg.get("model", "Qwen/Qwen2.5-7B-Instruct"))
    try:
        import requests
        resp = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": prompts["system"]},
                    {"role": "user", "content": prompts["user"]},
                ],
                "temperature": 0.1,
            },
            headers=_build_llm_headers(cfg),
            timeout=(12, 90),
        )
        if resp.status_code != 200:
            return {"error": f"LLM 返回错误：HTTP {resp.status_code} - {resp.text[:300]}"}
        data = resp.json()
        content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
        parsed = _extract_first_json_object(content)
        if not parsed:
            return {"error": "模型未返回可解析的 JSON，请重试或更换文档链接"}
        template = _normalize_template_payload(parsed, body.source_hint, body.cat_hint)
        if not template.get("apiName"):
            return {"error": "解析结果缺少 apiName，请手动补充后再保存"}
        return {
            "template": template,
            "remaining_calls": quota.get("remaining", -1),
            "doc_url": doc_url,
        }
    except requests.exceptions.Timeout:
        return {"error": "LLM 解析超时，请稍后重试"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api-template-from-url/stream")
async def api_template_from_url_stream(doc_url: str, source_hint: str = "tushare", cat_hint: str = "market"):
    """SSE 方式读取网页并流式返回模板解析进度与结果。"""
    def _sse(event: str, payload: Dict[str, Any]) -> str:
        # 统一 SSE 包装，前端按 event 名称分流处理。
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def event_stream():
        # 基础参数校验：统一通过 SSE error 事件回传，不直接抛 HTTP 错误页。
        url = str(doc_url or "").strip()
        if not url:
            yield _sse("error", {"message": "请先提供文档链接"})
            return
        cfg = sqlite_repo.get_active_llm_config()
        if not cfg:
            yield _sse("error", {"message": "请先在 AI 设置中配置并启用模型"})
            return
        if not cfg.get("base_url"):
            yield _sse("error", {"message": "请先在 AI 设置中填写 base_url"})
            return
        if (not _is_local_free_provider(cfg)) and (not _resolve_effective_api_key(cfg)):
            if _is_cloud_demo_provider(cfg):
                yield _sse("error", {"message": "当前环境未配置云端免费体验通道，请联系管理员设置 QS_ETL_DEMO_API_KEY，或手动填写 API Key。"})
            else:
                yield _sse("error", {"message": "请先在 AI 设置中配置 API Key"})
            return
        quota = _consume_cloud_demo_quota_if_needed(cfg)
        if not quota.get("ok"):
            yield _sse("error", {"message": quota.get("error"), "remaining_calls": quota.get("remaining", 0)})
            return

        yield _sse("progress", {"message": "正在抓取网页文档..."})
        try:
            doc_text = _extract_doc_text_from_url(url)
        except Exception as e:
            yield _sse("error", {"message": f"读取文档失败: {e}"})
            return

        yield _sse("progress", {"message": "正在调用大模型抽取模板..."})
        prompts = _build_api_template_prompts(url, source_hint, cat_hint, doc_text)
        base_url = str(cfg.get("base_url", "")).rstrip("/")
        model = str(cfg.get("model", "Qwen/Qwen2.5-7B-Instruct"))

        try:
            import requests
            content_acc = ""
            stream_supported = False
            # 优先尝试上游流式模式，若上游不支持会自动降级为非流式一次性解析。
            with requests.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompts["system"]},
                        {"role": "user", "content": prompts["user"]},
                    ],
                    "temperature": 0.1,
                    "stream": True,
                },
                headers=_build_llm_headers(cfg),
                timeout=(12, 90),
                stream=True,
            ) as resp:
                if resp.status_code == 200:
                    for raw_line in resp.iter_lines(decode_unicode=True):
                        line = str(raw_line or "").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk_obj = json.loads(payload)
                        except Exception:
                            continue
                        delta = ((chunk_obj.get("choices", [{}])[0] or {}).get("delta", {}) or {}).get("content", "")
                        if isinstance(delta, str) and delta:
                            stream_supported = True
                            content_acc += delta
                            yield _sse("delta", {"content": delta})
                else:
                    # 先记录错误文本，后续会进入 fallback 非流式路径尝试。
                    yield _sse("progress", {"message": f"上游流式不可用，准备降级（HTTP {resp.status_code}）..."})

            if (not stream_supported) or (not content_acc.strip()):
                # 降级：调用非流式接口，至少保证能返回最终模板结果。
                resp = requests.post(
                    f"{base_url}/chat/completions",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": prompts["system"]},
                            {"role": "user", "content": prompts["user"]},
                        ],
                        "temperature": 0.1,
                    },
                    headers=_build_llm_headers(cfg),
                    timeout=(12, 90),
                )
                if resp.status_code != 200:
                    yield _sse("error", {"message": f"LLM 返回错误：HTTP {resp.status_code} - {resp.text[:300]}"})
                    return
                data = resp.json()
                content_acc = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
                if isinstance(content_acc, str) and content_acc:
                    yield _sse("delta", {"content": content_acc})

            yield _sse("progress", {"message": "正在校验模板字段结构..."})
            parsed = _extract_first_json_object(content_acc)
            if not parsed:
                yield _sse("error", {"message": "模型未返回可解析的 JSON，请重试或更换文档链接"})
                return
            template = _normalize_template_payload(parsed, source_hint, cat_hint)
            if not template.get("apiName"):
                yield _sse("error", {"message": "解析结果缺少 apiName，请手动补充后再保存"})
                return
            yield _sse("final", {"template": template, "remaining_calls": quota.get("remaining", -1), "doc_url": url})
        except requests.exceptions.Timeout:
            yield _sse("error", {"message": "LLM 解析超时，请稍后重试"})
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/assistant-event")
async def assistant_event(body: AssistantEventCreate):
    """记录交互助手埋点事件，供体验优化与验收统计。"""
    event_id = str(uuid.uuid4())
    saved = sqlite_repo.save_ai_assistant_event({
        "id": event_id,
        "event_name": body.event_name,
        "scene": body.scene,
        "payload": body.payload,
    })
    return {"id": event_id, "event": saved}


@router.get("/assistant-events")
async def list_assistant_events(limit: int = 200):
    """查询最近的交互助手事件。"""
    return sqlite_repo.list_ai_assistant_events(limit=limit)


@router.get("/{cfg_id}")
async def get_one(cfg_id: str):
    data = sqlite_repo.get_llm_config(cfg_id)
    if not data:
        return {"error": "LLM 配置不存在"}
    return data


@router.delete("/{cfg_id}")
async def delete(cfg_id: str):
    deleted = sqlite_repo.delete_llm_config(cfg_id)
    return {"deleted": deleted}
