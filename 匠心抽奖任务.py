#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 匠心忠华 抽奖脚本
# token 内置在 TOKENS 列表中，支持多账号
import requests
import hashlib
import urllib.parse
import time
import json
from datetime import datetime

SALT = "superjing"

TOKENS = [
    "123"
]

H5_HEADERS = {
    "Host": "api.quwayouxuan.com",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "charset": "utf-8",
    "Origin": "https://qwh5w.jiangxinyouxuan.com",
    "Referer": "https://qwh5w.jiangxinyouxuan.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0xf254181d) XWEB/19749 miniProgram/wxddaa0832e6acc5f1"
}

H5_BASE_PARAMS = {
    "sj_h5": "1",
    "os": "h5",
    "version": "2.0.0",
}

IS_FREE = 1
DRAW_NUM = 10
LOTTERY_MAX_COUNT = 100
LOTTERY_INTERVAL = 3

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}")

def generate_h5_key(params):
    sorted_keys = sorted(params.keys())
    sign_str = ""
    for key in sorted_keys:
        if key != "key":
            sign_str += f"{key}={params[key]}"
    sign_str += SALT
    sign_str = sign_str.replace(" ", "")
    sha1 = hashlib.sha1()
    sha1.update(sign_str.encode('utf-8'))
    return sha1.hexdigest()

def make_h5_request(url, token, extra_params=None):
    try:
        current_time = str(int(time.time() * 1000))
        params = H5_BASE_PARAMS.copy()
        params["token"] = token
        params["current_time"] = current_time
        if extra_params:
            params.update(extra_params)
        params["key"] = generate_h5_key(params)

        post_body = urllib.parse.urlencode(params)
        response = requests.post(url, data=post_body, headers=H5_HEADERS, timeout=30)

        if response.status_code == 200:
            return response.json()
        log(f"  HTTP {response.status_code}")
        return None
    except Exception as e:
        log(f"  请求异常: {str(e)}")
        return None

def get_lottery_info(token):
    url = "https://api.quwayouxuan.com/lottery/api/limitedLotterySeries.do"
    result = make_h5_request(url, token)
    if result and result.get("code") == 1:
        data = result.get("data", {})
        user = data.get("user", {})
        free_count = data.get("free_count", 0)
        consume = data.get("activity", {}).get("consume", "100")
        log(f"  积分: {user.get('points', 0)} | 免费次数: {free_count} | 消耗: {consume}积分/次")
        return data
    else:
        msg = result.get("message", "未知错误") if result else "请求失败"
        log(f"  获取活动信息失败: {msg}")
    return None

def do_lottery_draw(token):
    url = "https://api.quwayouxuan.com/lottery/api/limitedLotteryDrawForSeries.do"
    result = make_h5_request(url, token, {
        "is_free": str(IS_FREE),
        "draw_num": str(DRAW_NUM)
    })

    if result and result.get("code") == 1:
        data = result.get("data", {})
        awards = data if isinstance(data, list) else data.get("award", data.get("awards", []))
        if isinstance(awards, list):
            total_pts = 0
            for award in awards:
                pts = int(award.get("points", award.get("rice", 0)) or 0)
                total_pts += pts
                title = award.get("product_title", "未知")
                status = award.get("winning_status", "")
                if pts:
                    log(f"    🎁 {title} +{pts}积分")
                elif status == 2:
                    log(f"    🎁 中实物: {title}")
                else:
                    log(f"    🎁 {title} (状态:{status})")
            log(f"    📊 本轮+{total_pts}积分")
        else:
            log(f"    🎁 抽奖成功: {json.dumps(data, ensure_ascii=False)[:300]}")
        return True
    else:
        msg = result.get("message", "未知错误") if result else "请求失败"
        code = result.get("code", 0) if result else 0
        log(f"    ❌ 抽奖失败: code={code} {msg}")
        return False

def process_account(token, index):
    log(f"\n{'='*50}")
    log(f"【账号{index}】")

    info = get_lottery_info(token)
    if not info:
        return

    success_count = 0
    for i in range(LOTTERY_MAX_COUNT):
        log(f"  🎰 第{i+1}次抽奖 (is_free={IS_FREE}, draw_num={DRAW_NUM})...")
        ok = do_lottery_draw(token)
        if ok:
            success_count += 1
        else:
            break
        time.sleep(LOTTERY_INTERVAL)

    log(f"  📊 抽奖完成: 成功{success_count}次")

    get_lottery_info(token)

def main():
    print(f"===== 匠心忠华 抽奖脚本 =====")
    print(f"执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模式: is_free={IS_FREE} | draw_num={DRAW_NUM} | 最大{LOTTERY_MAX_COUNT}次")
    print(f"内置账号: {len(TOKENS)}个")

    if not TOKENS:
        log("未配置 token，请在 TOKENS 列表中添加")
        return

    for idx, token in enumerate(TOKENS, 1):
        process_account(token, idx)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"异常: {str(e)}")
