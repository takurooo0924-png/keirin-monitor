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
    log(f"--- 最終突破フェーズ開始: {now.strftime('%H:%M:%S')} ---")
    
    date_hyphen = now.strftime('%Y-%m-%d')
    races_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 (表を無視した「文字あさり」抽出) ---
        try:
            log("【競輪】Kドリームスへ潜入中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(7000)
            
            soup = BeautifulSoup(await page.content(), "html.parser")
            blocks = soup.find_all(class_="kaisai-list")
            log(f"  -> 開催ブロックを {len(blocks)} 個検出")
            
            for block in blocks:
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                log(f"    - {track_name} の文字情報を解析...")
                
                # ブロック内の全テキストを取得し、改行や空白を整理
                full_text = block.get_text(separator=' ', strip=True)
                # 「1R 21:25」のようなパターンを、表構造を無視して直接探す
                matches = re.findall(r'(\d+R).*?(\d{1,2}:\d{2})', full_text)
                
                for r_num, t_str in matches:
                    # 同じレース番号付近に「結果」の文字がないかチェック
                    context_snippet = full_text[full_text.find(r_num):full_text.find(r_num)+30]
                    if "結果" not in context_snippet:
                        races_data.append({"track": track_name, "race_num": r_num, "time_str": t_str})
                log(f"      => {track_name}: {len(matches)} 件の候補を発見")
        except Exception as e:
            log(f"【競輪】エラー: {e}")

        # --- 2. オート (「しつこい監視」抽出) ---
        tracks_auto = {"飯塚": "iizuka", "川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            log(f"【オート】{name} をチェック中...")
            try:
                url = f"https://autorace.jp/race_info/Program/{roma}/{date_hyphen}_12/program"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # 2秒おきに最大10回、HTMLの中身に時刻が隠れていないか確認する
                found_time = None
                for i in range(10):
                    content = await page.content()
                    m = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                    if m:
                        found_time = m.group(1)
                        break
                    await page.wait_for_timeout(2000)
                
                if found_time:
                    races_data.append({"track": f"{name}オート", "race_num": "12R", "time_str": found_time})
                    log(f"    => {name} 12R: {found_time} 取得！")
                else:
                    log(f"    -> {name}: 20秒粘りましたが、数字が隠蔽されています")
            except: continue

        await browser.close()

    # --- 共通保存処理 ---
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"], "race_num": r["race_num"], "time_str": r["time_str"], "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"--- 最終集計: {len(parsed_results)} 件を保存します ---")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)
    log("--- 全工程終了 ---")

if __name__ == "__main__":
    asyncio.run(fetch_data())
