# 合规落地包审计 + 改造规划

## 审计基准文档
`docs/ETL工具 全套合规落地包（MD版）.md`

## 现状审计

### ✅ 已实现（无需改动）
| 文档要求 | 代码位置 | 状态 |
|---------|---------|------|
| 机器码 + 激活码绑定 | `backend/app/core/license_manager.py:76-119` | ✅ 已实现（CPU+VolumeSerial+hostname+user 哈希） |
| 版本权限矩阵 | `license_manager.py:21-73`, `etl_tool_sdk/license.py:20-43` | ✅ 已实现（free/personal/professional 三级） |
| License API | `backend/app/api/license.py` | ✅ 在线/离线激活、解绑、功能检查 |
| SDK LicenseManager | `backend/etl_tool_sdk/license.py` | ✅ 已实现 |
| host 默认 127.0.0.1 | `backend/app/tray_app.py:1045` | ✅ uvicorn.Config(host="127.0.0.1") |
| About 免责声明 | `index.html:1235-1242` | ✅ 有 5 条基础免责声明 |
| AI 合规通知 | AI 生成结果自带 compliance_notice | ✅ |
| 本地加密存储 | SQLite metadata 表 | ✅ |
| 无强制联网校验 | 校验全在本地 | ✅ |

### ❌ 未实现 / 不符合要求（需改造）
| # | 文档要求 | 现状 | 风险 | 优先级 |
|---|---------|------|------|-------|
| 1 | **CORS 仅允许 127.0.0.1/内网** | `allow_origins=["*"]` 全开放 | 高 | P0 |
| 2 | **API 页面合规提示文案** | 无任何提示 | 高 | P0 |
| 3 | **完整用户协议** | 只有 5 条免责，非文档中 7 条完整版 | 中 | P1 |
| 4 | **API 限流（单IP限频）** | 无 rate limiting 中间件 | 中 | P1 |
| 5 | **API 调用审计日志** | 无本地审计落库 | 中 | P1 |
| 6 | **免费版禁用 API/调度/多任务** | 全开放，无 gating | 中 | P1 |
| 7 | **代码层强制屏蔽 0.0.0.0** | 仅未使用，无硬编码禁止 | 低 | P2 |
| 8 | **企业版** | 仅 free/personal/professional，无 enterprise | 低 | P2 |
| 9 | **API 返回数据不返回原始裸数据** | 无字段脱敏/重映射约束 | 低 | P2 |

### ✅ 通达信直连合规整改（已完成）
| 项目 | 改动 | 状态 |
|------|------|------|
| `tdx_adapter.py` | 删除所有 pytdx 网络连接代码，改为本地 .lc/.dat 文件解析 | ✅ 已完成 |
| `/api/kline-sources/tdx/benchmark` | 删除整个端点 | ✅ 已完成 |
| `index.html` 前端 | 服务器选择+批量测速 → 本地数据目录路径输入 | ✅ 已完成 |
| `index.html` JS | 删除 onTdxServerSelect、benchmarkTdxServers、selectFastServer | ✅ 已完成 |
| `index.html` 文案 | 删除"免费/公开/无需注册"等违规文案 | ✅ 已完成 |
| `build.spec` | 从 hiddenimports 移除 pytdx、pytdx.hq | ✅ 已完成 |

---

## 改造方案（按优先级）

### P0：安全合规（必须立即改）

#### 1. CORS 收紧
**文件**: `backend/app/main.py`
```python
# 当前: allow_origins=["*"]
# 改为:
app.add_middleware(CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
```

#### 2. API 页面合规提示
**文件**: `index.html` — API 参考弹窗顶部增加固定提示：
> ⚠️ 本接口仅限用户本机/内部局域网系统自用，禁止暴露公网、禁止对外分发金融行情数据，违规使用责任自负。

#### 3. tray_app.py 启动日志增加合规提示
在 `tray_app.py` 浏览器打开后日志加一行：
```
print("合规提示: 本服务默认仅监听 127.0.0.1，禁止暴露至公网")
```

### P1：功能完善（下一批次开发）

#### 4. API 限流中间件
新建 `backend/app/middleware/rate_limiter.py`:
- 基于内存字典的简单限流（轻量，不引入 slowapi）
- 默认：100 次/分钟/IP
- 配置文件可调整
- 挂载到 `/api/*` 路由

#### 5. API 审计日志
新建 `backend/app/middleware/api_audit.py`:
- 拦截所有 `/api/*` 请求
- 记录：时间、IP、路径、方法、耗时、状态码
- 写入 SQLite 新表 `api_audit_log`
- 保留最近 30 天（自动清理）

#### 6. 免费版功能限制
**文件**: `license_manager.py` + 各 API 入口
- 免费用户禁用定时调度（已有 scheduler 检查，加强）
- 免费用户 API 返回 403（可选：或返回精简数据）
- 在 `pipelines` 和 `workflows` API 增加 `check_feature_or_raise`

### P2：强化（有空再做）

#### 7. 0.0.0.0 硬编码禁止
在 `tray_app.py` 的 uvicorn.Config 调用前加断言：
```python
assert host != "0.0.0.0", "安全限制：禁止监听 0.0.0.0"
```

#### 8. 完整版用户协议
将文档中的 7 条完整版用户协议放入 About 页面的「用户协议」折叠面板（不影响现有免责声明）。

---

## 后续开发基准清单

### 已确认的架构约定（不得违背）
1. **host 永远只监听 127.0.0.1**，任何代码变更不得改为 0.0.0.0
2. **License 不引入强制联网校验**，所有校验本地完成
3. **用户数据、Token、原始行情不上传任何外网服务器**
4. **SDK 不提供第三方数据源对接逻辑**，仅为工具能力封装
5. **版本类型**: free / personal / professional（文档写 enterprise，代码用 professional，以后者为准）

### 关键文件清单
- `backend/app/core/license_manager.py` — 授权核心
- `backend/app/api/license.py` — 授权 API
- `backend/etl_tool_sdk/license.py` — SDK 授权封装
- `backend/app/main.py` — FastAPI 应用入口 + CORS
- `backend/app/tray_app.py` — 启动 + uvicorn 配置
- `backend/app/static/index.html` — 前端 UI
- `backend/app/persistence/sqlite_repo.py` — 数据持久化
