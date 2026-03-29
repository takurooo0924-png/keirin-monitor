import asyncio
from playwright.async_api import async_playwright

async def debug_scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 海外からのアクセスを怪しまれないための設定
        context = await browser.new_context(user_agent="Mozilla/5.0")
        page = await context.new_page()

        # 1. 競輪サイトを撮影
        print("競輪サイトへ移動中...")
        await page.goto("https://my.keirin.kdreams.jp/kaisai/")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="keirin_view.png", full_page=True)

        # 2. 飯塚オートを撮影（今日の日付で）
        print("オートレースサイトへ移動中...")
        # ※日付は自動で今日になります
        from datetime import datetime
        import pytz
        today = datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d')
        await page.goto(f"https://autorace.jp/race_info/Program/iizuka/{today}_12/program")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="auto_view.png", full_page=True)

        await browser.close()
        print("撮影完了！")

if __name__ == "__main__":
    asyncio.run(debug_scrape())
