#!/usr/bin/env python3
"""激活码生成器 -- 仅开发者使用。

使用 Ed25519 私钥签名，生成合法激活码。

用法：
    # 生成个人版永久激活码
    python gen_license.py personal

    # 生成个人版年度激活码
    python gen_license.py personal --expires 2027-08-15

    # 生成专业版永久激活码
    python gen_license.py professional

    # 生成会员共享码（知识星球用）
    python gen_license.py personal --expires 2026-12-31 --label zsxq-member

    # 批量生成
    python gen_license.py personal --count 5 --expires 2027-12-31
"""
import sys
import argparse
from datetime import datetime
from pathlib import Path

# 私钥文件路径
SCRIPT_DIR = Path(__file__).resolve().parent
PRIVATE_KEY_PATH = SCRIPT_DIR / "license_private_key.pem"


def load_private_key():
    """加载 Ed25519 私钥。"""
    from cryptography.hazmat.primitives import serialization

    if not PRIVATE_KEY_PATH.exists():
        print(f"[error] 私钥文件不存在: {PRIVATE_KEY_PATH}")
        print("请先生成密钥对")
        sys.exit(1)

    pem_data = PRIVATE_KEY_PATH.read_bytes()
    private_key = serialization.load_pem_private_key(pem_data, password=None)
    return private_key


def sign_activation(private_key, lic_type: str, expires: str) -> str:
    """使用私钥签名激活码。"""
    message = f"{lic_type}:{expires}".encode("utf-8")
    signature = private_key.sign(message)
    return signature.hex()


def generate_code(private_key, lic_type: str, expires: str = "lifetime") -> str:
    """生成完整激活码。格式: type:expires:signature"""
    sig = sign_activation(private_key, lic_type, expires)
    return f"{lic_type}:{expires}:{sig}"


def main():
    parser = argparse.ArgumentParser(description="生成金智汇联 ETL 激活码")
    parser.add_argument("type", choices=["personal", "professional"],
                        help="License 类型")
    parser.add_argument("--expires", default="lifetime",
                        help="过期日期 (YYYY-MM-DD) 或 'lifetime' (默认)")
    parser.add_argument("--count", type=int, default=1,
                        help="批量生成数量")
    parser.add_argument("--label", default="",
                        help="标签（用于区分不同渠道，如 zsxq-member）")
    args = parser.parse_args()

    private_key = load_private_key()

    print(f"=== 金智汇联 ETL 激活码生成器 ===")
    print(f"类型: {args.type}")
    print(f"过期: {args.expires}")
    if args.label:
        print(f"标签: {args.label}")
    print(f"数量: {args.count}")
    print()

    codes = []
    for i in range(args.count):
        code = generate_code(private_key, args.type, args.expires)
        codes.append(code)
        suffix = f" [{args.label}]" if args.label else ""
        print(f"  {i+1}. {code}{suffix}")

    print()
    print(f"共生成 {len(codes)} 个激活码")

    # 保存到文件
    output_path = SCRIPT_DIR / "generated_codes.txt"
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"\n# {datetime.now().isoformat()} | {args.type} | {args.expires}")
        if args.label:
            f.write(f" | {args.label}")
        f.write("\n")
        for code in codes:
            f.write(f"{code}\n")
    print(f"已追加到: {output_path}")


if __name__ == "__main__":
    main()
