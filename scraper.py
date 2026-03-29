import asyncio
import json
import re
from datetime import datetime, timedelta
import pytz
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def fetch_data():
    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    print(f"--- 実行開始: {now.strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    date_hyphen = now.strftime('%Y-%m-%d')
    races_data = []

    async with async_playwright() as p:
        print("ブラウザを起動しています...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        page = await context.new_page()

        # --- 1. 競輪 ---
        try:
            print("【競輪】Kドリームスを開いています...")
            await page.goto("https://my.keirin.kdreams.jp/kaisai/", timeout=60000)
            await page.wait_for_timeout(7000)
            
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            blocks = soup.find_all(class_="kaisai-list")
            print(f"【競輪】開催ブロックを {len(blocks)} 個見つけました")
            
            for block in blocks:
                track_tag = block.find(class_="velodrome")
                if not track_tag: continue
                track_name = track_tag.get_text(strip=True).replace("競輪", "")
                print(f"  -> 競輪場: {track_name} を解析中...")
                
                tables = block.find_all("table")
                print(f"    - 表を {len(tables)} 個検出")
                for tbl in tables:
                    try:
                        df = pd.read_html(StringIO(str(tbl)))[0]
                        print(f"    - 表の行数: {len(df)}")
                        for _, row in df.iterrows():
                            r_num = str(row.iloc[0])
                            if "R" in r_num:
                                time_m = re.search(r'(\d{1,2}:\d{2})', str(row.iloc[1]))
                                if time_m and "結果" not in str(row.iloc[1]):
                                    races_data.append({"track": track_name, "race_num": r_num, "time_str": time_m.group(1)})
                    except Exception as tbl_e:
                        print(f"    - 表の解析に失敗: {tbl_e}")
        except Exception as e:
            print(f"【競輪】致命的なエラー: {e}")

        # --- 2. オート ---
        tracks_auto = {"飯塚": "iizuka", "川口": "kawaguchi", "伊勢崎": "isesaki", "浜松": "hamamatsu", "山陽": "sanyou"}
        for name, roma in tracks_auto.items():
            print(f"【オート】{name} のページを確認中...")
            try:
                url = f"https://autorace.jp/race_info/Program/{roma}/{date_hyphen}_12/program"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                print(f"  -> {name}: 投票締切の文字を待っています...")
                try:
                    await page.wait_for_selector("text=投票締切", timeout=15000)
                    print(f"  -> {name}: 文字を検出しました！")
                    
                    content = await page.content()
                    m = re.search(r'投票締切\s*(\d{1,2}:\d{2})', content)
                    if m:
                        races_data.append({"track": f"{name}オート", "race_num": "12R", "time_str": m.group(1)})
                        print(f"  -> {name}: {m.group(1)} を取得")
                except:
                    print(f"  -> {name}: タイムアウト（数字が出ませんでした）")
            except Exception as auto_e:
                print(f"  -> {name}: ページ移動エラー: {auto_e}")

        await browser.close()

    print(f"【集計】有効なレースを合計 {len(races_data)} 件見つけました")
    
    # 保存処理
    parsed_results = []
    for r in races_data:
        h, m = map(int, r["time_str"].split(':'))
        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now.hour >= 20 and h < 5: dt += timedelta(days=1)
