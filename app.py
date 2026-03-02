from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime
import collections
import os
import random

app = Flask(__name__)
CORS(app)

def fetch_winwin_data(target_date=None):
    date_str = target_date if target_date else datetime.now().strftime('%Y-%m-%d')
    api_url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://winwin.tw/Bingo"
    }
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def get_strategy_recom(history_draws, mode="adaptive"):
    """
    進階預測演算法：
    1. 隔期跳號 (Skip-Draw)：找前前開過但前一期沒開的。
    2. 尾數過濾 (Tail-Filter)：確保四個號碼尾數不重複超過 2 個。
    3. 連號補償：加入一組高機率連號。
    """
    if len(history_draws) < 3: return [1, 2, 3, 4]
    
    # 提取數據層
    last_1 = set(history_draws[-1]) # 上一期
    last_2 = set(history_draws[-2]) # 前一期
    all_recent = [n for d in history_draws[-15:] for n in d]
    counts = collections.Counter(all_recent)
    
    # 邏輯 A：隔期跳號 (重點追蹤)
    skip_nums = list(last_2 - last_1)
    
    # 邏輯 B：熱門號與冷門號
    hot_candidates = [item[0] for item in counts.most_common(15)]
    cold_candidates = sorted(list(range(1, 81)), key=lambda x: counts[x])[:15]

    pool = []
    if mode == "aggressive":
        # 激進：2熱 + 1跳 + 1隨機熱
        pool = hot_candidates[:10] + skip_nums[:5]
    elif mode == "defensive":
        # 防守：2冷 + 1跳 + 1熱
        pool = cold_candidates[:10] + skip_nums[:5] + hot_candidates[:5]
    else:
        # 自適應 (混合核心)：1熱 + 1冷 + 2跳
        pool = hot_candidates[:5] + cold_candidates[:5] + skip_nums

    # 執行過濾：確保尾數分散 (避免 12, 22, 32 同時出現)
    final_selection = []
    random.shuffle(pool)
    
    tails_used = []
    for n in pool:
        tail = n % 10
        if tails_used.count(tail) < 2: # 同尾數最多只取兩個
            final_selection.append(n)
            tails_used.append(tail)
        if len(final_selection) == 4: break
            
    # 如果湊不滿 4 個，用熱門號補齊
    while len(final_selection) < 4:
        for h in hot_candidates:
            if h not in final_selection:
                final_selection.append(h)
                break
                
    return sorted(final_selection)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    target_date = request.args.get('date')
    raw_data = fetch_winwin_data(target_date)
    if not raw_data: return jsonify({"status": "error"}), 500

    processed = []
    for item in raw_data:
        processed.append({
            "no": item.get('No'),
            "nums": [int(n) for n in item.get('BigShowOrder', '').split(',')],
            "super": int(item.get('BullEyeTop', 0)),
            "time": item.get('OpenDate').split('T')[1][:5]
        })
    processed.sort(key=lambda x: x['no'])

    # 數據統計：連開、遺漏、連號 (略，同前版本)...
    streaks = {i: {"hit": 0, "miss": 0} for i in range(1, 81)}
    for i in range(1, 81):
        for d in reversed(processed):
            if i in d['nums']:
                if streaks[i]['miss'] == 0: streaks[i]['hit'] += 1
                else: break
            else:
                if streaks[i]['hit'] == 0: streaks[i]['miss'] += 1
                else: break

    hot_streaks = [{"num": k, "val": v['hit']} for k, v in streaks.items() if v['hit'] >= 2]
    cold_streaks = [{"num": k, "val": v['miss']} for k, v in streaks.items() if v['miss'] >= 5]
    
    pair_streaks = {}
    for n in range(1, 80):
        miss = 0
        for d in reversed(processed):
            if n in d['nums'] and n+1 in d['nums']: break
            miss += 1
        if miss >= 5: pair_streaks[f"{n}-{n+1}"] = miss

    correlations = collections.Counter()
    for d in processed:
        draw_list = sorted(d['nums'])
        for i in range(len(draw_list)):
            for j in range(i + 1, len(draw_list)):
                correlations[(draw_list[i], draw_list[j])] += 1
    top_corr = [{"pair": f"{p[0]}, {p[1]}", "count": c} for p, c in correlations.most_common(5)]

    # 推薦與回測
    comparison_history = []
    win_count = 0
    final_draws_list = [d['nums'] for d in processed]
    
    for i in range(len(processed)):
        curr = processed[i]
        hist_before = final_draws_list[:i]
        sugg = get_strategy_recom(hist_before, "adaptive")
        matches = set(sugg) & set(curr['nums'])
        is_win = len(matches) >= 2
        if is_win: win_count += 1
        comparison_history.append({
            "no": curr['no'], "time": curr['time'], "nums": curr['nums'],
            "super": curr['super'], "suggestion": [str(x).zfill(2) for x in sugg], 
            "match": len(matches), "is_win": is_win
        })

    return jsonify({
        "status": "success",
        "hot_streaks": sorted(hot_streaks, key=lambda x: x['val'], reverse=True)[:10],
        "cold_streaks": sorted(cold_streaks, key=lambda x: x['val'], reverse=True)[:10],
        "pair_missing": dict(sorted(pair_streaks.items(), key=lambda x: x[1], reverse=True)[:8]),
        "correlations": top_corr,
        "super_recom": [str(n).zfill(2) for n in [random.randint(1,80) for _ in range(4)]], # 佔位邏輯
        "next_recom": {
            "adaptive": [str(x).zfill(2) for x in get_strategy_recom(final_draws_list, "adaptive")],
            "aggressive": [str(x).zfill(2) for x in get_strategy_recom(final_draws_list, "aggressive")],
            "defensive": [str(x).zfill(2) for x in get_strategy_recom(final_draws_list, "defensive")]
        },
        "live_win_rate": round((win_count / len(processed)) * 100, 1) if processed else 0,
        "history": comparison_history[::-1][:25]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
