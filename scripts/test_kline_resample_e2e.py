"""Playwright 端到端测试 — 验证 kline_resample 节点在前端能正常工作。

测试步骤：
  1. 启动 FastAPI 后端（8080 端口）
  2. 打开 workflow-editor 页面
  3. 验证左侧"指标计算"分类下有 "K线任意分钟合成"
  4. 拖拽到画布
  5. 点击节点，验证右侧属性面板渲染出所有参数字段
  6. 修改分钟数 = 90，保存工作流，重新加载，验证参数持久化
"""
import os
import sys
import time
import signal
import subprocess
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"


def _wait_for_server(url: str, timeout: int = 30) -> bool:
    """轮询直到服务可访问。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def start_backend():
    """启动后端服务作为子进程，返回 Popen 对象。"""
    # 如果端口已被占用（已在运行的服务），直接复用
    if _wait_for_server("http://127.0.0.1:8080/", timeout=3):
        print("[test] 检测到已在运行的后端服务，复用")
        return None
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.Popen(
        [sys.executable, "run_server.py"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if not _wait_for_server("http://127.0.0.1:8080/api/workflows/nodes", timeout=30):
        proc.terminate()
        raise RuntimeError("后端服务启动失败")
    print("[test] 后端服务已启动")
    return proc


def stop_backend(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    print("[test] 后端服务已停止")


def run_tests():
    from playwright.sync_api import sync_playwright

    proc = start_backend()
    failures = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1400, "height": 900})
            page = context.new_page()

            # 捕获 console 和 request 错误
            page_errors = []
            page.on("console", lambda m: page_errors.append(f"[{m.type}] {m.text}")
                     if m.type in ("error",) else None)

            # ---- Step 1: 打开 editor 页面 ----
            print("[test] Step 1: 打开 workflow-editor")
            page.goto("http://127.0.0.1:8080/workflow-editor.html", wait_until="networkidle")
            page.wait_for_timeout(2000)

            # ---- Step 2: 左侧 palette 有 kline_resample ----
            print("[test] Step 2: 验证左侧节点面板有 'K线任意分钟合成'")
            item = page.locator(".palette-item[data-type='kline_resample']")
            if item.count() != 1:
                failures.append("左侧面板未找到 kline_resample 节点")
            else:
                label = item.inner_text()
                if "K线任意分钟合成" not in label:
                    failures.append(f"节点 label 不正确：'{label}'")
                else:
                    print("[test]   找到节点：OK")

            # ---- Step 3: 拖拽到画布 ----
            print("[test] Step 3: 拖拽节点到画布")
            editor = page.locator("#drawflow")
            if item.count() == 1:
                box = editor.bounding_box()
                item.drag_to(editor, target_position={"x": 400, "y": 200})
                page.wait_for_timeout(1000)
                # 检查画布上是否出现节点
                node_on_canvas = page.locator(".drawflow .drawflow-node").first
                try:
                    node_on_canvas.wait_for(timeout=3000)
                    print("[test]   节点已添加到画布")
                except Exception as e:
                    failures.append(f"节点未成功添加到画布: {e}")

            # ---- Step 4: 点击节点，验证属性面板 ----
            print("[test] Step 4: 点击节点，打开属性面板")
            if item.count() == 1:
                first_node = page.locator(".drawflow .drawflow-node").first
                first_node.click()
                page.wait_for_timeout(800)
                # 验证属性面板里的字段
                props_panel = page.locator("#props-panel")
                for field_label in ["目标分钟数", "时间字段", "分组字段", "对齐模式", "交易时段", "丢弃未完成"]:
                    if props_panel.locator(f"text={field_label}").count() == 0:
                        failures.append(f"属性面板缺少字段：{field_label}")
                    else:
                        print(f"[test]   字段存在：{field_label}")

            # ---- Step 5: 修改分钟数 ----
            print("[test] Step 5: 修改分钟数为 90")
            if item.count() == 1:
                min_input = page.locator("#props-panel input[data-param='minutes']")
                if min_input.count() == 1:
                    min_input.fill("90")
                    min_input.dispatch_event("change")
                    page.wait_for_timeout(500)
                    val = min_input.input_value()
                    if val != "90":
                        failures.append(f"分钟数未成功修改为 90，当前值：'{val}'")
                else:
                    failures.append("未找到分钟数输入框")

            # ---- Step 6: 验证对齐模式下拉 ----
            print("[test] Step 6: 验证对齐模式下拉选项")
            mode_select = page.locator("#props-panel select[data-param='mode']")
            if mode_select.count() == 1:
                opts = mode_select.locator("option").all_inner_texts()
                opts = [o.strip() for o in opts]
                print(f"[test]   下拉选项：{opts}")
                if len(opts) < 2:
                    failures.append(f"对齐模式选项数不对：{opts}")
            else:
                failures.append("未找到对齐模式 select")

            # ---- Step 7: 保存工作流 + 重新加载验证持久化 ----
            print("[test] Step 7: 保存工作流后重新加载，验证参数持久化")
            # 触发保存按钮
            save_btn = page.locator("button", has_text="保存")
            if save_btn.count() >= 1:
                save_btn.first.click()
                page.wait_for_timeout(1500)
                # 重新加载页面
                page.goto("http://127.0.0.1:8080/workflow-editor.html", wait_until="networkidle")
                page.wait_for_timeout(2000)
                # 点击刚才的节点
                first_node = page.locator(".drawflow .drawflow-node").first
                if first_node.count() >= 1:
                    first_node.click()
                    page.wait_for_timeout(800)
                    val = page.locator("#props-panel input[data-param='minutes']").input_value()
                    if val != "90":
                        failures.append(f"参数持久化失败，重加载后值：'{val}'")
                    else:
                        print("[test]   参数持久化成功")

            # 打印 console errors
            if page_errors:
                print("\n[console errors]")
                for e in page_errors[:20]:
                    print("  ", e)

            browser.close()
    finally:
        stop_backend(proc)

    if failures:
        print("\n[FAIL] 测试失败：")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    else:
        print("\n[PASS] 所有 Playwright 测试通过")


if __name__ == "__main__":
    run_tests()
