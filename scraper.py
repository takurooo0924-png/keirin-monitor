import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

def log(msg):
    print(msg, flush=True)

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    log(f"--- 3/30 デバッグ開始: {now.strftime('%H:%M:%S')} ---")
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 1200}
        )
        page = await context.new_page()

        try:
            log("【競輪】Kドリームスへ潜入中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(10000) # 読み込みをしっかり待つ
            
            # 証拠写真を撮影
            await page.screenshot(path="debug_kdreams.png", full_page=True)
            log("  -> 画面撮影完了 (debug_kdreams.png)")

            soup = BeautifulSoup(await page.content(), "html.parser")
            # 会場ごとのブロックを取得
            blocks = soup.select(".kaisai-list")
            log(f"  -> 発見した開催場数: {len(blocks)}")

            for block in blocks:
                track_tag = block.select_one(".velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                
                # 行ごとにスキャン（レース番号と時刻のペアを探す）
                rows = block.select("tr")
                for row in rows:
                    txt = row.get_text(separator=' ', strip=True)
                    # 「数字R」と「00:00」が同じ行にあるものを抽出
                    m = re.search(r'(\d+R).*?(\d{1,2}:\d{2})', txt)
                    if m and "結果" not in txt and "終了" not in txt:
                        races_data.append({
                            "track": track_name, 
                            "race_num": m.group(1), 
                            "time_str": m.group(2)
                        })
            
            log(f"  -> 捕捉件数: {len(races_data)} 件")

        except Exception as e:
            log(f"【エラー】: {e}")
        await browser.close()

    # --- 未来のレースだけを抽出 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # 深夜実行時、お昼のレースを「昨日のレース（過去）」と判定しないための補正
        if dt < now - timedelta(hours=6):
            dt += timedelta(days=1)
        
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], 
                "race_num": r["race_num"], 
                "time_str": r["time_str"], 
                "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を保存 ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
