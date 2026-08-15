# License 系统安全架构

## 密钥分离

```
┌─────────────────────────────────┐     ┌──────────────────────────────┐
│  开源仓库 (quantsync-etl)        │     │  闭源仓库 (quantsync-pro)     │
│                                 │     │                              │
│  ✅ Ed25519 公钥（验证用）        │     │  🔒 Ed25519 私钥（签名用）     │
│  ✅ _verify_activation()        │     │  🔒 gen_license.py           │
│  ✅ activate_online()           │     │  🔒 license_private_key.pem  │
│  ❌ 无 generate_activation_code │     │  ✅ generate_activation_code │
│  ❌ 无签名密钥                   │     │                              │
└─────────────────────────────────┘     └──────────────────────────────┘
         │                                        │
         │  公钥可以验证，但无法生成                   │  私钥可以签名生成
         │  ← 安全性保障                            │  ← 仅开发者可访问
```

**原理**：Ed25519 非对称加密
- 私钥签名 → 生成激活码
- 公钥验证 → 校验激活码
- 公钥公开无安全风险（无法反推私钥）

## 开发者工作流

### 生成激活码

```bash
cd D:/04.量化/quantsync-pro

# 个人版永久
python gen_license.py personal

# 个人版年度（知识星球会员共享）
python gen_license.py personal --expires 2027-12-31 --label zsxq-2027

# 专业版永久（闲鱼单次购买）
python gen_license.py professional --label xianyu-user001

# 批量生成
python gen_license.py personal --count 10 --expires 2027-12-31
```

生成的激活码格式：
```
personal:2027-12-31:a7c5b1fb281c1f19439619d70f9916c7e8f368dd5b3e6e6706c8b79b107644e8b26ffe752dee00f5524b75c95146e8e4a2b154db5ed281e23922357fe870f700
```

### 激活码分发

| 渠道 | 码类型 | 说明 |
|------|--------|------|
| 知识星球 | 共享码 | 所有会员共用，带标签 `zsxq-YYYY`，到期统一失效 |
| 闲鱼 | 独立码 | 一用户一码，带标签 `xianyu-xxx`，永久有效 |

## 用户使用流程

```
1. 用户在应用中看到 "升级专业版" 入口
2. 通过知识星球/闲鱼购买
3. 开发者在闭源仓库运行 gen_license.py 生成激活码
4. 将激活码发给用户
5. 用户在应用 "License 管理" 中输入激活码
6. 应用使用公钥验证签名 → 激活成功
```

## 验证测试

```bash
# 在闭源仓库生成
cd D:/04.量化/quantsync-pro
python gen_license.py personal --expires 2027-12-31

# 复制生成的激活码

# 在开源仓库验证
cd D:/04.量化/quantsync-etl/backend
python -c "
from app.core.license_manager import _verify_activation
code = '粘贴激活码'
parts = code.split(':')
result = _verify_activation(parts[0], parts[1], parts[2])
print(f'Verify: {result}')
"
```

## 安全保证

| 攻击方式 | 是否可行 | 原因 |
|----------|----------|------|
| 从开源代码生成激活码 | ❌ 不可行 | 无私钥 |
| 修改验证逻辑绕过 | ⚠️ 可能 | 但修改代码后失去升级动力 |
| 反推私钥 | ❌ 不可行 | Ed25519 密码学安全 |
| 复制他人的激活码 | ⚠️ 可能 | 可通过机器码绑定缓解 |

## 文件清单

### 开源仓库
- `backend/app/core/license_manager.py` — 验证逻辑 + 公钥

### 闭源仓库
- `license_private_key.pem` — Ed25519 私钥
- `gen_license.py` — 激活码生成脚本
- `generated_codes.txt` — 已生成的激活码记录
