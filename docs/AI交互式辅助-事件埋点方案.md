# AI交互式辅助-事件埋点方案（P0）

## 1. 埋点目标
- 衡量 AI 辅助是否显著降低操作门槛。
- 识别高失败环节（凭证/连接/数据源/工作流）。
- 为后续提示词、流程和默认值优化提供数据依据。

## 2. 事件模型

### 2.1 事件表结构（已落地）
- 表名：`ai_assistant_events`
- 字段：
  - `id`：事件主键
  - `event_name`：事件名
  - `scene`：场景（credential/datasource/connection/workflow）
  - `payload_json`：事件上下文
  - `created_at`：事件时间

### 2.2 API
- `POST /api/llm/assistant-event`：写入事件
- `GET /api/llm/assistant-events?limit=200`：查询最近事件

## 3. 事件清单（P0 必采）
- `assistant_opened`
  - 触发：打开 AI 助手弹窗
  - payload：`mode`
- `assistant_guidance_generated`
  - 触发：成功生成建议
  - payload：`mode`, `hasError`
- `assistant_action_applied`
  - 触发：点击快捷动作并成功回填/跳转
  - payload：`selector`, `value`（敏感信息需脱敏）

## 4. 指标口径
- 助手触达率：`assistant_opened / 场景总访问次数`
- 建议生成成功率：`assistant_guidance_generated / assistant_opened`
- 快捷动作采用率：`assistant_action_applied / assistant_guidance_generated`
- 故障场景转化率：
  - 分母：测试失败次数（连接/凭证）
  - 分子：失败后触发 `assistant_opened(mode=troubleshoot)` 次数

## 5. 数据安全与合规
- 不记录明文 token、密码、API key。
- `payload_json` 中涉及敏感字段必须脱敏或截断。
- 所有埋点仅本地 SQLite 存储，不上传第三方服务（P0）。

## 6. 分析建议（周报）
- 按 scene 统计：
  - 失败后是否打开助手
  - 打开后是否使用快捷动作
  - 使用快捷动作后是否再次失败（需结合测试结果日志）
- 对高失败字段建立“默认值优化”白名单（如 base_url、port）。
