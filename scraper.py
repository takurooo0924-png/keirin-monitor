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
    log(f"--- 3/30 最終検証スキャン: {now.strftime('%H:%M:%S')} ---")
    
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            log("【競輪】Kドリームスへ接続中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # デバッグ写真は継続（証拠用）
            await page.screenshot(path="debug_kdreams.png", full_page=True)

            # Playwrightの機能で直接テキストを引っこ抜く（隙間に強い）
            blocks = await page.query_selector_all(".kaisai-list")
            log(f"  -> 開催場を {len(blocks)} 件検出")

            for block in blocks:
                # 会場名を取得
                track_tag = await block.query_selector(".velodrome")
                if not track_tag: continue
                track_name = (await track_tag.inner_text()).replace("競輪", "").strip()
                
                # その会場内の全テキストを「そのまま」取得
                text = await block.inner_text()
                
                # 番号: 数字の後に「R」（間に何があってもOK）
                found_races = re.findall(r'(\d+)\s*R', text)
                # 時刻: 数字 記号 数字（全角・半角・空白すべてを個別キャッチ）
                found_times = re.findall(r'(\d{1,2})\s*[:：]\s*(\d{2})', text)
                
                log(f"    - {track_name}: 番号{len(found_races)} / 時刻{len(found_times)}")

                # 数が合う場合のみ順番にペアリング
                if len(found_races) > 0 and len(found_races) <= len(found_times):
                    for i in range(len(found_races)):
                        r_num = found_races[i] + "R"
                        t_str = f"{found_times[i][0]}:{found_times[i][1]}"
                        
                        races_data.append({
                            "track": track_name, 
                            "race_num": r_num, 
                            "time_str": t_str
                        })
            
            log(f"  -> 合計 {len(races_data)} 件の抽出に成功")

        except Exception as e:
            log(f"【実行エラー】: {e}")
        await browser.close()

    # --- 未来のレースだけを保存 ---
    parsed_results = []
    for r in races_data:
        try:
            h, m = map(int, r["time_str"].split(':'))
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            
            if dt < now - timedelta(hours=6):
                dt += timedelta(days=1)
            
            if dt > now:
                parsed_results.append({
                    "id": f"{r['track']}_{r['race_num']}",
                    "track": r["track"], "race_num": r["race_num"], "time_str": r["time_str"], "deadline": dt.isoformat()
                })
        except:
            continue

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を確定 ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(fetch_data())
