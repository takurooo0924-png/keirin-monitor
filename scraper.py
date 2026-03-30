import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    print("【調査開始】Kドリームスのページ構造を解析します...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
        page = await context.new_page()
        
        try:
            # 競輪のページへアクセス
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle")
            await page.wait_for_timeout(3000)
            
            # ページ内の「場名」と「テーブル構造」を根こそぎ取得するJS
            js_code = """
            () => {
                let debugInfo = { 
                    url: document.location.href, 
                    track_links: [],
                    tables: [] 
                };
                
                // 1. 「競輪」という文字を含むリンク（場名）のクラスと親要素を調査
                let links = Array.from(document.querySelectorAll('a')).filter(a => a.innerText.includes('競輪'));
                debugInfo.track_links = links.map(a => ({ 
                    text: a.innerText.trim(), 
                    className: a.className, 
                    parentClass: a.parentElement ? a.parentElement.className : "none" 
                }));

                // 2. ページ内のすべてのテーブルの「1R」の列（最初の列）のHTML構造を調査
                let tables = document.querySelectorAll('table');
                tables.forEach((tbl, idx) => {
                    // テーブルを囲っている外枠のクラス名を3階層上まで取得
                    let parentClasses = [];
                    let curr = tbl.parentElement;
                    for(let i=0; i<3 && curr; i++) {
                        if(curr.className) parentClasses.push(curr.className);
                        curr = curr.parentElement;
                    }
                    
                    // テーブルの近くにあるテキスト（場名を特定する手がかり）
                    let trackContext = "";
                    let wrapper = tbl.closest('div, section');
                    if (wrapper) {
                        trackContext = wrapper.innerText.substring(0, 30).replace(/\\n/g, ' '); 
                    }

                    // 1Rの列の5つの行（tr）の中身を調査
                    let tbody = tbl.querySelector('tbody');
                    let trs = tbody ? tbody.querySelectorAll('tr') : [];
                    let firstColData = [];
                    
                    trs.forEach((tr, trIdx) => {
                        if(trIdx > 5) return; // 最初の数行だけで構造は分かる
                        let firstCell = tr.querySelectorAll('td')[0];
                        firstColData.push({
                            row: trIdx + 1,
                            html: firstCell ? firstCell.innerHTML.trim().replace(/\\n/g, '') : "セルなし",
                            text: firstCell ? firstCell.innerText.trim().replace(/\\n/g, ' | ') : "テキストなし"
                        });
                    });

                    debugInfo.tables.push({
                        table_index: idx,
                        parents: parentClasses.join(" < "),
                        context: trackContext,
                        row_count: trs.length,
                        column_1R_structure: firstColData
                    });
                });

                return debugInfo;
            }
            """
            
            debug_info = await page.evaluate(js_code)
            
            # 結果をGitHubのログに綺麗に出力
            print("========== 【解析結果（ここから下をコピーしてください）】 ==========", flush=True)
            print(json.dumps(debug_info, ensure_ascii=False, indent=2), flush=True)
            print("========== 【解析結果（ここまで）】 ==========", flush=True)
            
        except Exception as e:
            print(f"エラー発生: {e}", flush=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
