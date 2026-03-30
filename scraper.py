import asyncio
from playwright.async_api import async_playwright

async def main():
    print("【HTML取得開始】Kドリームスの生HTMLを取得します...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
        page = await context.new_page()
        
        try:
            # 競輪のページへアクセス
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle")
            await page.wait_for_timeout(3000)
            
            # 生のHTMLを取得し、ログ容量削減のため不要なタグを掃除するJS
            js_code = """
            () => {
                let clone = document.body.cloneNode(true);
                
                // 構造解析に関係ないノイズ（スクリプト、装飾、画像、SVGなど）を徹底的に削除
                let trashes = clone.querySelectorAll('script, style, svg, img, iframe, noscript, path');
                trashes.forEach(t => t.remove());
                
                // フッターの不要なリンク群なども極力削る（解析対象はメインコンテンツなので）
                let footers = clone.querySelectorAll('footer, .l-footer');
                footers.forEach(f => f.remove());

                return clone.innerHTML;
            }
            """
            
            raw_html = await page.evaluate(js_code)
            
            # 行数を減らすために空白行を詰める
            lines = [line.strip() for line in raw_html.split('\n') if line.strip()]
            clean_html = '\n'.join(lines)
            
            print("========== 【HTML抽出結果（ここから）】 ==========", flush=True)
            print(clean_html, flush=True)
            print("========== 【HTML抽出結果（ここまで）】 ==========", flush=True)
            
        except Exception as e:
            print(f"エラー発生: {e}", flush=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
