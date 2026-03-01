from flask import Flask, render_template, jsonify
import requests
from datetime import datetime
import collections

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/strategy')
def strategy():
    today = datetime.now().strftime('%Y-%m-%d')
    api_url = f"https://winwin.tw/Bingo/GetBingoData?date={today}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        raw_data = response.json()

        # 整理數據
        all_draws = []
        super_nums = []
        for item in raw_data:
            nums = [int(n) for n in item.get('BigShowOrder', '').split(',')]
            all_draws.append(nums)
            super_nums.append(int(item.get('BullEyeTop', 0)))

        # 計算熱門號
        flat_nums = [n for d in all_draws for n in d]
        hot_nums = [item[0] for item in collections.Counter(flat_nums).most_common(10)]

        # 計算超級獎號尾數
        tails = [s % 10 for s in super_nums]
        tail_counts = [collections.Counter(tails).get(i, 0) for i in range(10)]

        return jsonify({
            "status": "success",
            "hot_nums": hot_nums,
            "tail_distribution": tail_counts,
            "sample_size": len(raw_data)
        })
    except:
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
