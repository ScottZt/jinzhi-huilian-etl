"""
使用 Playwright 为操作手册截取各页面截图。
截图保存为 PNG，宽度 1440px，按页面功能分文件夹。
"""
import os, sys, time, asyncio
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:8080"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "static", "guide_images")

PAGES = [
    ("overview", "overview.png"),
    ("kline-sources", "kline_sources.png"),
    ("connections", "connections.png"),
    ("schemas", "schemas.png"),
    ("workflows", "workflows.png"),
    ("pipelines", "pipelines.png"),
    ("bulk-import", "bulk_import.png"),
    ("tasks", "tasks.png"),
    ("monitor", "monitor.png"),
    ("ai-script", "ai_script.png"),
    ("llm-settings", "llm_settings.png"),
    ("logs", "logs.png"),
]

async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # 总览页
        await page.screenshot(path=os.path.join(OUT_DIR, "overview.png"), full_page=False)

        for view, filename in PAGES:
            if view == "overview":
                continue
            try:
                await page.click(f'[data-view="{view}"]', timeout=3000)
                await page.wait_for_timeout(1200)
                await page.screenshot(path=os.path.join(OUT_DIR, filename), full_page=False)
                print(f"  ✓ {view} -> {filename}")
            except Exception as e:
                print(f"  ✗ {view} -> {filename}: {e}")

        # 工作流编辑器
        try:
            await page.click('[data-view="workflows"]', timeout=3000)
            await page.wait_for_timeout(1000)
            # 如果有工作流，打开第一个编辑器
            edit_btn = page.locator('text=编辑').first
            if await edit_btn.count() > 0:
                await edit_btn.click()
                await page.wait_for_timeout(2000)
                await page.screenshot(path=os.path.join(OUT_DIR, "workflow_editor.png"), full_page=False)
                print("  ✓ workflow editor")
            else:
                # 点击新建
                new_btn = page.locator('text=新建工作流').first
                if await new_btn.count() > 0:
                    await new_btn.click()
                    await page.wait_for_timeout(2000)
                    await page.screenshot(path=os.path.join(OUT_DIR, "workflow_editor.png"), full_page=False)
                    print("  ✓ workflow editor (new)")
        except Exception as e:
            print(f"  ✗ workflow editor: {e}")

        # 数据源新建弹窗
        try:
            await page.click('[data-view="kline-sources"]', timeout=3000)
            await page.wait_for_timeout(800)
            new_btn = page.locator('text=新建数据源').first
            if await new_btn.count() > 0:
                await new_btn.click()
                await page.wait_for_timeout(800)
                await page.screenshot(path=os.path.join(OUT_DIR, "kline_source_new.png"), full_page=False)
                print("  ✓ kline source new dialog")
        except Exception as e:
            print(f"  ✗ kline source new: {e}")

        # 连接管理新建弹窗
        try:
            await page.click('[data-view="connections"]', timeout=3000)
            await page.wait_for_timeout(800)
            new_btn = page.locator('text=新建连接').first
            if await new_btn.count() > 0:
                await new_btn.click()
                await page.wait_for_timeout(800)
                await page.screenshot(path=os.path.join(OUT_DIR, "connection_new.png"), full_page=False)
                print("  ✓ connection new dialog")
        except Exception as e:
            print(f"  ✗ connection new: {e}")

        await browser.close()
    print(f"\nDone. Screenshots saved to: {OUT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
