import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import sys

# 実況ログを即座に表示するための関数
def log(msg):
    print(msg, flush=True)

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    log(f"--- 実行開始: {now.strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    date_hyphen = now.strftime('%Y-%m-%d')
    races_data = []

    async with async_playwright() as p:
        log("ブラウザを起動しています...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 ---
        try:
            log("【競輪】Kドリームスにアクセス中...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            log("  -> ページ読み込み完了。5秒待機します...")
            await page.wait_for_timeout(5000)
            
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            blocks = soup.find_all(class_="kaisai-list")
            log(f"  -> 開催ブロックを {len(blocks)} 個見つけました")
            
            for block in blocks:
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                log(f"    - {track_name} を解析中...")
                
                tables = block.find_all("table")
                for tbl in tables:
                    try:
                        df = pd.read_html(StringIO(str(tbl)))[0]
                        for _, row in df.iterrows():
                            r_num = str(row.iloc[0])
                            if "R" in r_num:
                                time_m = re.search(r'(\d{1,2}:\d{2})', str(row.iloc[1]))
                                if time_m and "結果" not in str(row.iloc[1]):
                                    races_data.append({"track": track_name, "race_num": r_num, "time_str": time_m.group(1)})
                    except Exception as tbl_e:
                        log(f"      ! 表の解析でエラー: {tbl_e}")
        except Exception as e:
            log(f"【競輪】致命的エラー: {e}")

        # --- 2. オート ---
        tracks_auto = {"飯塚": "iizuka", "川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            log(f"【オート】{name} のページへ移動...")
            try:
                url = f"https://autorace.jp/race_info/Program/{roma}/{date_hyphen}_12/program"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                log(f"  -> {name}: '投票締切' の文字を待機中（最大20秒）...")
                try:
                    await page.wait_for_selector("text=投票締切", timeout=20000)
                    log(f"  -> {name}: 文字を発見！抽出します。")
                    
                    content = await page.content()
                    m = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                    if m:
                        races_data.append({"track": f"{name}オート", "race_num": "12R", "time_str": m.group(1)})
                        log(f"    => {name} 12R: {m.group(1)} 取得成功")
                except:
                    log(f"  -> {name}: タイムアウト（数字が出ませんでした）")
            except Exception as auto_e:
                log(f"  -> {name}: ページ移動エラー: {auto_e}")

        await browser.close()

    log(f"--- 抽出完了: 合計 {len(races_data)} 件 ---")
    
    # 保存処理
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
        if dt > now:
            parsed_results.append({
                "id": f"{r['track']}_{r['race_num']}",
                "track": r["track"],
                "race_num": r["race_num"],
                "time_str": r["time_str"],
                "deadline": dt.isoformat()
            })

    parsed_results.sort(key=lambda x: x["deadline"])
    log(f"【保存】{len(parsed_results)} 件を schedule.json に書き込みます")
    
    with open('schedule.json', 'w', encoding='utf-8') as f:
        json.dump(parsed_results, f, ensure_ascii=False, indent=2)
    log("--- 全工程終了 ---")

if __name__ == "__main__":
    asyncio.run(fetch_data())
