# 商业化流程测试计划

## 前置准备

### 1. 环境准备
```bash
# 确保在开源仓库目录
cd D:/04.量化/quantsync-etl

# 确认 Python 环境
python --version

# 确认依赖已安装
pip install -r backend/requirements.txt
```

### 2. 数据准备
```bash
# 清理旧数据（可选）
# 删除 backend/data/quantsync.db 重置数据库

# 确认内容包文件存在
ls D:/04.量化/quantsync-etl/pro-content/金智汇联专业版内容包_v1.jspack
```

---

## 测试场景

### 场景 1：开发者模式测试（完整功能）

**目标**：验证开发者可以导入内容包并使用所有功能

**步骤**：
```bash
# 1. 启动服务（开发者模式）
JZHL_DEV_MODE=true python backend/run_server.py

# 2. 打开浏览器访问 http://localhost:8000
```

**验证项**：
- [ ] 1.1 License 状态显示"开发者模式"或正常显示版本
- [ ] 1.2 进入「License 管理」页面
- [ ] 1.3 上传 `.jspack` 文件
- [ ] 1.4 预览显示：25 个工作流 + 6 个插件
- [ ] 1.5 点击「确认导入」
- [ ] 1.6 导入成功提示
- [ ] 1.7 工作流列表显示 25 个专业工作流
- [ ] 1.8 插件中心显示 6 个高级官方插件
- [ ] 1.9 导入示例工作流弹框中，专业版示例可勾选导入

---

### 场景 2：免费版测试（无 License）

**目标**：验证免费版用户的限制

**步骤**：
```bash
# 1. 启动服务（非开发者模式）
python backend/run_server.py

# 2. 打开浏览器访问 http://localhost:8000
```

**验证项**：
- [ ] 2.1 License 状态显示"免费基础版"
- [ ] 2.2 内置预设（6 个）可正常使用
- [ ] 2.3 尝试上传 `.jspack` 文件 → **应提示需要付费版 License**
- [ ] 2.4 工作流列表只有内置预设
- [ ] 2.5 插件中心无高级官方插件
- [ ] 2.6 导入示例弹框中：
  - [ ] 内置预设可勾选
  - [ ] 专业版示例显示"🔒 专业版"标签
  - [ ] 专业版示例显示"需导入专业版内容包"提示

---

### 场景 3：付费版测试（激活码 + 内容包）

**目标**：验证完整的付费用户流程

**步骤**：
```bash
# 1. 生成测试激活码
python -c "from backend.app.core.license_manager import generate_activation_code; print(generate_activation_code('personal', '2026-12-31'))"

# 2. 复制输出的激活码（格式：personal:2026-12-31:xxxxx）

# 3. 启动服务（非开发者模式）
python backend/run_server.py

# 4. 打开浏览器访问 http://localhost:8000
```

**验证项**：
- [ ] 3.1 进入「License 管理」页面
- [ ] 3.2 输入激活码 → 点击「激活」
- [ ] 3.3 License 状态变为"个人版"
- [ ] 3.4 上传 `.jspack` 文件
- [ ] 3.5 预览正常显示
- [ ] 3.6 点击「确认导入」→ 成功
- [ ] 3.7 工作流列表显示所有工作流
- [ ] 3.8 插件中心显示 6 个高级插件

---

### 场景 4：开源仓库安全性验证

**目标**：确认专业版工作流 JSON 不会通过 View Source 泄露

**步骤**：
```bash
# 1. 启动服务
python backend/run_server.py

# 2. 打开浏览器，访问示例导入弹框
```

**验证项**：
- [ ] 4.1 按 F12 打开开发者工具
- [ ] 4.2 查看 Network 标签，找到 `example_workflows.js`
- [ ] 4.3 检查文件内容：
  - [ ] 每个示例只有 `id`, `title`, `description`, `tags`
  - [ ] **没有** `workflow` 字段（或 `workflow` 为 null/undefined）
- [ ] 4.4 在 Console 执行：
  ```javascript
  console.log(window.EXAMPLE_WORKFLOWS[0].workflow)
  // 应输出 undefined
  ```
- [ ] 4.5 检查 `content-registry.js`：
  - [ ] `isPro(1)` 返回 `true`
  - [ ] `needsPack(1)` 返回 `true`

---

### 场景 5：插件功能验证

**目标**：验证导入的插件可正常工作

**前置**：已完成场景 1 或场景 3，成功导入内容包

**验证项**：
- [ ] 5.1 新建工作流
- [ ] 5.2 拖入 `outlier_handler` 节点
- [ ] 5.3 配置参数并运行预览
- [ ] 5.4 插件正常执行，无报错
- [ ] 5.5 对其他 5 个插件重复上述测试

---

### 场景 6：内容包重复导入

**目标**：验证重复导入的行为

**步骤**：
```bash
# 假设已完成一次内容包导入
```

**验证项**：
- [ ] 6.1 再次上传相同的 `.jspack` 文件
- [ ] 6.2 导入结果提示"跳过 X 个已存在"
- [ ] 6.3 工作流列表无重复项

---

## 测试报告模板

| 场景 | 状态 | 备注 |
|------|------|------|
| 1. 开发者模式 | ☐ 通过 ☐ 失败 | |
| 2. 免费版限制 | ☐ 通过 ☐ 失败 | |
| 3. 付费版流程 | ☐ 通过 ☐ 失败 | |
| 4. 开源安全 | ☐ 通过 ☐ 失败 | |
| 5. 插件功能 | ☐ 通过 ☐ 失败 | |
| 6. 重复导入 | ☐ 通过 ☐ 失败 | |

---

## 快速测试命令

```bash
# 开发者模式快速测试
cd D:/04.量化/quantsync-etl
JZHL_DEV_MODE=true python backend/run_server.py

# 生成测试激活码
python -c "from backend.app.core.license_manager import generate_activation_code; print(generate_activation_code('personal', '2026-12-31'))"

# 重建内容包（如果修改了专业版内容）
cd D:/04.量化/quantsync-etl/pro-content
python build_pack.py v1
```
