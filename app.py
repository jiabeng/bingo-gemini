from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime
import collections
import os

app = Flask(__name__)
CORS(app)

def fetch_winwin_data(target_date=None):
    date_str = target_date if target_date else datetime.now().strftime('%Y-%m-%d')
    api_url = f"https://winwin.tw/Bingo/GetBingoData?date={date_str}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://winwin.tw/Bingo"}
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        return response.json() if response.status_code == 200 else None
    except: return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    target_date = request.args.get('date')
    raw_data = fetch_winwin_data(target_date)
    if not raw_data: return jsonify({"status": "error"}), 500

    # 排序：從舊到新 (計算連續性必須依序)
    processed = []
    for item in raw_data:
        processed.append({
            "no": item.get('No'),
            "nums": set([int(n) for n in item.get('BigShowOrder', '').split(',')]),
            "super": int(item.get('BullEyeTop', 0)),
            "time": item.get('OpenDate').split('T')[1][:5]
        })
    processed.sort(key=lambda x: x['no'])

    # --- 1. 號碼遺漏與連開分析 ---
    streaks = {i: {"hit": 0, "miss": 0} for i in range(1, 81)}
    for i in range(1, 81):
        count = 0
        # 由新往舊找
        for d in reversed(processed):
            if i in d['nums']:
                if streaks[i]['miss'] == 0: streaks[i]['hit'] += 1
                else: break
            else:
                if streaks[i]['hit'] == 0: streaks[i]['miss'] += 1
                else: break

    # 篩選：連開 2 期以上 / 遺漏 5 期以上
    hot_streaks = [{"num": k, "val": v['hit']} for k, v in streaks.items() if v['hit'] >= 2]
    cold_streaks = [{"num": k, "val": v['miss']} for k, v in streaks.items() if v['miss'] >= 5]

    # --- 2. 連號遺漏分析 ---
    pair_streaks = {} # (n, n+1) -> miss_count
    for n in range(1, 80):
        pair = (n, n+1)
        miss = 0
        for d in reversed(processed):
            if n in d['nums'] and n+1 in d['nums']: break
            miss += 1
        if miss >= 5: pair_streaks[f"{n}-{n+1}"] = miss

    # --- 3. 同時出現頻率 (Pair Correlation) ---
    # 找出今天最常「一起出現」的組合
    correlations = collections.Counter()
    for d in processed:
        draw_list = sorted(list(d['nums']))
        for i in range(len(draw_list)):
            for j in range(i + 1, len(draw_list)):
                correlations[(draw_list[i], draw_list[j])] += 1
    
    top_correlations = []
    for (n1, n2), count in correlations.most_common(5):
        top_correlations.append({"pair": f"{n1}, {n2}", "count": count})

    return jsonify({
        "status": "success",
        "hot_streaks": sorted(hot_streaks, key=lambda x: x['val'], reverse=True)[:10],
        "cold_streaks": sorted(cold_streaks, key=lambda x: x['val'], reverse=True)[:10],
        "pair_missing": dict(sorted(pair_streaks.items(), key=lambda x: x[1], reverse=True)[:8]),
        "correlations": top_correlations,
        "history": [ {**d, "nums": sorted(list(d['nums']))} for d in processed[::-1][:20]]
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
