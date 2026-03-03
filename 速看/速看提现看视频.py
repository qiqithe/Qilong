# -*- coding: utf-8 -*-
"""
脚本名称: 速看免费小说 每号每日0.3（新增新人7天签到）
修改：1. 移除自动提现 2. 新增新人7天签到接口 3. 先执行签到再执行刷任务
二次修改：1. 新增新人签到状态校验，避免重复签到返回30028 2. 优化签到错误码识别逻辑
本脚本仅供学习研究使用，严禁用于任何商业、刷量、违规获利等行为。
使用本脚本所产生的一切风险、账号封禁、法律责任及后果，均由使用者自行承担。
作者仅提供代码参考，不承担任何相关责任。使用即代表您已阅读并同意本声明。
脚本更新链接 记得转存实时更新：https://pan.quark.cn/s/c6416fe69380
修复优化：
1. 增加了信号处理，解决了无法立即停止的问题。
2. 增加了子线程异常捕获，解决了任务瞬间结束且无日志的问题。
3. 默认任务轮数调整为45次，匹配实际稳定执行进度
4. 新增：先执行新人7天签到（task_type=105），再执行原有任务
5. 已移除：自动提现逻辑、任务同步、提现等待
6. 新增：签到前校验今日是否已签到，避免30028错误

建议用微信登录 然后绑定手机号 随便看几下小说再抓包 防止黑号
需要有限时不扣余额的0.3提现入口 没有的不能玩 建议换号
当天提现之后就不要再刷了，不然会黑号
可以边刷边看进度 进度满了就提现别刷了

环境变量说明:
    [必须]
    SUKAN_URL: 账号数据，支持换行或@分割。
    抓 https://welfare-user.palmestore.com/api/user/ 域名 整段完整url放进来就行

    [可选]
    SUKAN_TASK_LOOP:   任务执行轮数 (默认: 45)
    SUKAN_MIN_WAIT:    单轮任务最小等待秒数 (默认: 15)
    SUKAN_MAX_WAIT:    单轮任务最大等待秒数 (默认: 20)
    SUKAN_TIMEOUT:     网络请求超时时间，单位毫秒 (默认: 10000)
    SUKAN_PROXY_API:   代理提取API地址
    SUKAN_CONCURRENCY: 并发线程数量 (默认: 1)
"""

import os
import sys
import time
import random
import json
import re
import logging
import urllib.parse
import signal
import threading
import requests
from dataclasses import dataclass
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

# 关闭SSL警告
requests.packages.urllib3.disable_warnings()

STOP_EVENT = threading.Event()

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

logger = logging.getLogger("SuKan")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

if not logger.handlers:
    logger.addHandler(handler)

@dataclass
class AppConfig:
    SUKAN_URL: str
    TASK_LOOP_TIMES: int
    MIN_WAIT_SEC: int
    MAX_WAIT_SEC: int
    TIMEOUT: float
    PROXY_API: str
    CONCURRENCY: int

    @classmethod
    def load_from_env(cls) -> "AppConfig":
        url_data = os.environ.get('SUKAN_URL')
        if not url_data:
            logger.error("❌ 严重错误: 未设置环境变量 SUKAN_URL")
            return None

        return cls(
            SUKAN_URL=url_data,
            TASK_LOOP_TIMES=int(os.environ.get('SUKAN_TASK_LOOP', 45)),
            MIN_WAIT_SEC=int(os.environ.get('SUKAN_MIN_WAIT', 18)),
            MAX_WAIT_SEC=int(os.environ.get('SUKAN_MAX_WAIT', 20)),
            TIMEOUT=int(os.environ.get('SUKAN_TIMEOUT', 10000)) / 1000,
            PROXY_API=os.environ.get('SUKAN_PROXY_API', ''),
            CONCURRENCY=int(os.environ.get('SUKAN_CONCURRENCY', 1)),
        )

CFG = AppConfig.load_from_env()

def signal_handler(signum, frame):
    signame = signal.Signals(signum).name
    logger.warning(f"🛑 接收到信号 {signame}，正在通知所有线程停止...")
    STOP_EVENT.set()

class Utils:
    @staticmethod
    def get_random_ua() -> str:
        os_map = {'10': 'QP1A', '11': 'RP1A', '12': 'SP1A', '13': 'TP1A', '14': 'UP1A'}
        models = [
            '23049RAD8C', '22041211AC', '22011211C', '2106118C',
            'V2055A', 'V2185A', 'V2241A', 'V2118A',
            'PCDM10', 'PDEM30', 'PGEM10', 'PGFM10',
            'RMX3366', 'RMX3560', 'RMX3706',
            'HMA-AL00', 'TAS-AN00', 'ANA-AN00', 'LGE-AN00'
        ]
        android_ver = random.choice(list(os_map.keys()))
        build_prefix = os_map[android_ver]
        model = random.choice(models)
        date_part = f"{random.randint(20, 23)}{random.randint(1, 12):02d}{random.randint(1, 28):02d}"
        build_id = f"{build_prefix}.{date_part}.{random.randint(10, 999):03d}"
        chrome_major = random.randint(110, 126)
        chrome_ver = f"{chrome_major}.0.{random.randint(5000, 6500)}.{random.randint(100, 200)}"
        return (f"Mozilla/5.0 (Linux; Android {android_ver}; {model} Build/{build_id}; wv) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{chrome_ver} "
                f"Mobile Safari/537.36 zyApp/SuKanRead zyVersion/8.0.2 zyChannel/801004")

class ProxyManager:
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.current_proxy: Optional[Dict[str, str]] = None

    def _extract_proxy_from_text(self, text: str) -> Optional[str]:
        if "://" in text:
            return text.strip()

        match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5})', text)
        return match.group(1) if match else None

    def refresh(self) -> Optional[Dict[str, str]]:
        if not self.api_url or STOP_EVENT.is_set():
            return None
        try:
            logger.info("🔄 [代理] 正在请求新IP...")
            resp = requests.get(self.api_url, timeout=5)
            content = resp.text
            proxy_str = None

            if "socks" in content or "://" in content:
                proxy_str = self._extract_proxy_from_text(content)

            if not proxy_str:
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        if 'data' in data and isinstance(data['data'], list) and data['data']:
                            item = data['data'][0]
                            proxy_str = f"{item.get('ip', item.get('IP'))}:{item.get('port', item.get('PORT'))}"
                        elif 'ip' in data and 'port' in data:
                            proxy_str = f"{data['ip']}:{data['port']}"
                except ValueError:
                    pass

            if not proxy_str:
                proxy_str = self._extract_proxy_from_text(content)

            if proxy_str:
                if "://" in proxy_str:
                    self.current_proxy = {'http': proxy_str, 'https': proxy_str}
                else:
                    self.current_proxy = {'http': f'http://{proxy_str}', 'https': f'http://{proxy_str}'}

                logger.info(f"✅ [代理] 获取成功: {proxy_str}")
                return self.current_proxy
            else:
                logger.warning(f"⚠️ [代理] 解析失败，API响应: {content[:100]}")
                return None
        except Exception as e:
            logger.error(f"❌ [代理] 请求异常: {e}")
            return None

class SuKanTaskWorker:
    def __init__(self, index: int, raw_input: str):
        self.idx = index
        self.raw_input = raw_input.strip()
        self.params: Dict[str, Any] = {}
        self.is_valid = False
        self.proxy_mgr = ProxyManager(CFG.PROXY_API)
        self.ua = Utils.get_random_ua()
        self.session = requests.Session()
        self._parse_input()
        self.raw_url = self.raw_input if self.raw_input.startswith('http') else ''

    def _parse_input(self):
        try:
            if self.raw_input.startswith('{'):
                data = json.loads(self.raw_input)
                body = data.get('body', {})
                token = body.get('token') or body.get('kt')
                zid = body.get('zyeid') or body.get('zyeId')
                if token and zid:
                    logger.info(f"[账号{self.idx}] 识别为 JSON 格式")
                    self.params = {'kt': token, 'zyeid': zid, 'usr': body.get('signUser', '')}
                    self.is_valid = True
                    return
        except Exception:
            pass

        try:
            qs = self.raw_input.split('?', 1)[1] if '?' in self.raw_input else self.raw_input
            parsed = urllib.parse.parse_qs(qs)
            self.params = {k: v[0] for k, v in parsed.items()}
            if not self.params.get('zyeid') and self.params.get('zyeId'):
                self.params['zyeid'] = self.params['zyeId']
            
            # 补充签到接口需要的参数（从抓包数据提取）
            if 'p35' in parsed:
                self.params['smboxid'] = parsed['p35'][0]
            self.params['id'] = f"{int(time.time() * 1000)}000023"  # 时间戳生成的id
            
            if self.params.get('zyeid') and self.params.get('kt'):
                self.is_valid = True
            else:
                logger.error(f"❌ [账号{self.idx}] 数据缺失: 未找到 zyeid 或 kt")
        except Exception as e:
            logger.error(f"❌ [账号{self.idx}] 数据解析异常: {e}")

    def _wait_random(self):
        sec = random.randint(CFG.MIN_WAIT_SEC, CFG.MAX_WAIT_SEC)
        logger.info(f"[账号{self.idx}] ⏳ 等待 {sec} 秒...")
        
        if STOP_EVENT.wait(timeout=sec):
            logger.info(f"[账号{self.idx}] 🛑 停止等待，准备退出")
            return

    def _send_request(self, method: str, url: str, data: dict = None, headers: dict = None, retry: int = 1) -> dict:
        if STOP_EVENT.is_set():
            return {}

        if CFG.PROXY_API and not self.proxy_mgr.current_proxy:
            self.proxy_mgr.refresh()

        req_headers = headers.copy() if headers else {}
        req_headers['User-Agent'] = self.ua

        try:
            resp = self.session.request(
                method=method, url=url, data=data, params=data if method == 'GET' else None,
                headers=req_headers, proxies=self.proxy_mgr.current_proxy, timeout=CFG.TIMEOUT
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if STOP_EVENT.is_set(): return {}
            
            err_msg = str(e)
            is_net_err = any(x in err_msg.lower() for x in ['timeout', 'connection', '502', '503', 'socks'])
            if is_net_err and retry > 0 and CFG.PROXY_API:
                logger.warning(f"[账号{self.idx}] ⚠️ 网络/代理异常 ({err_msg})，切换代理重试...")
                self.proxy_mgr.refresh()
                return self._send_request(method, url, data, headers, retry - 1)
            raise e

    # ========== 新增：校验新人7天签到状态 ==========
    def check_sign_status(self) -> bool:
        """
        校验今日是否已完成新人7天签到
        返回：True=已签到，False=未签到/校验失败
        """
        if STOP_EVENT.is_set(): return True
        
        # 福利任务列表接口（获取签到状态）
        api_url = 'https://welfare-user.palmestore.com/api/task/welfare/list'
        payload = self.params.copy()
        payload.update({
            'source': 'welfare', 
            'showContentInStatusBar': '1', 
            'ecpmMix': '0.0',
            'ecpmVideo': '0.0', 
            'mcTacid': ''
        })
        headers = {
            'Host': 'welfare-user.palmestore.com',
            'Referer': 'https://welfare-user.palmestore.com/sukanread/welfare-package/sudu/welfare.html'
        }
        
        try:
            resp_data = self._send_request('GET', api_url, data=payload, headers=headers)
            if not resp_data or resp_data.get('code') != 0:
                logger.warning(f"[账号{self.idx}] ⚠️ 签到状态校验失败，将尝试提交签到 | 原因: {resp_data.get('msg', '接口返回异常')}")
                return False
            
            # 解析新人签到状态（适配不同返回结构）
            tasks = resp_data.get('body', {}).get('tasks', [])
            for task in tasks:
                # 匹配新人7天签到任务（task_type=105 或 任务名称包含新人/7天）
                if task.get('task_type') == '105' or '新人' in task.get('task_name', '') or '7天' in task.get('task_name', ''):
                    done_status = task.get('done_status', 0)
                    # done_status=2 通常表示已完成，1表示未完成
                    if done_status == 2:
                        logger.info(f"[账号{self.idx}] 📌 签到状态校验：今日已完成新人7天签到，无需重复提交")
                        return True
                    else:
                        logger.info(f"[账号{self.idx}] 📌 签到状态校验：今日未签到，将执行签到")
                        return False
            
            # 未找到新人签到任务，尝试提交
            logger.warning(f"[账号{self.idx}] ⚠️ 未在任务列表中找到新人7天签到任务，将尝试提交签到")
            return False
        except Exception as e:
            logger.warning(f"[账号{self.idx}] ⚠️ 签到状态校验异常，将尝试提交签到 | 错误: {str(e)}")
            return False

    # 优化：新人7天签到任务执行函数（增加错误码处理）
    def execute_sign_task(self):
        if STOP_EVENT.is_set(): return

        # 第一步：先校验签到状态
        if self.check_sign_status():
            return

        # 第二步：执行签到提交
        api_url = 'https://welfare-user.palmestore.com/api/task/receive'
        payload = self.params.copy()
        payload.update({
            'source': 'welfare', 
            'showContentInStatusBar': '1', 
            'ecpmMix': '0.0',
            'ecpmVideo': '0.0', 
            'mcTacid': '', 
            'task_type': '105',  # 新人7天签到任务类型
            'receive_type': '2', 
            'reward_ecpm': '9.5600004196167'
        })
        # 签到接口专属Referer
        headers = {
            'Host': 'welfare-user.palmestore.com',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://welfare-user.palmestore.com/sukanread/welfare-package/sudu/welfare.html'
        }
        try:
            resp_data = self._send_request('POST', api_url, data=payload, headers=headers)
            if not STOP_EVENT.is_set():
                code = resp_data.get('code', '未知')
                msg = resp_data.get('msg', '未知')
                # 针对性处理30028错误
                if code == 30028 and '领取失败' in msg:
                    logger.info(f"[账号{self.idx}] 📌 新人7天签到 | 返回码: {code} | 消息: {msg} | 原因：大概率是今日已签到/新人周期过期")
                else:
                    logger.info(f"[账号{self.idx}] 🎉 新人7天签到完成 | 返回码: {code} | 消息: {msg}")
        except Exception as e:
            if not STOP_EVENT.is_set():
                logger.error(f"[账号{self.idx}] ❌ 新人7天签到失败: {e}")

    def execute_task(self, loop_num: int):
        if STOP_EVENT.is_set(): return

        api_url = 'https://welfare-user.palmestore.com/api/task/receive'
        payload = self.params.copy()
        payload.update({
            'source': 'welfare', 'showContentInStatusBar': '1', 'ecpmMix': '0.0',
            'ecpmVideo': '0.0', 'mcTacid': '', 'task_type': '518',
            'receive_type': '2', 'reward_ecpm': '9.5600004196167'
        })
        headers = {
            'Host': 'welfare-user.palmestore.com',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://welfare-user.palmestore.com/sukanread/welfare-package/withdraw-accumulate/index.html'
        }
        try:
            self._send_request('POST', api_url, data=payload, headers=headers)
            if not STOP_EVENT.is_set():
                logger.info(f"[账号{self.idx}] ✅ [第{loop_num}次] 任务完成")
        except Exception as e:
            if not STOP_EVENT.is_set():
                logger.error(f"[账号{self.idx}] ❌ [第{loop_num}次] 任务失败: {e}")

    def run(self):
        if not self.is_valid:
            return
            
        if CFG.PROXY_API:
            self.proxy_mgr.refresh()

        device_name = self.ua.split(';')[2].strip()
        logger.info(f"[账号{self.idx}] 🚀 启动 | 设备: {device_name} | 计划: {CFG.TASK_LOOP_TIMES}次")

        # ========== 第一步：先执行新人7天签到（已优化） ==========
        if not STOP_EVENT.is_set():
            logger.info(f"[账号{self.idx}] 📝 开始执行新人7天签到任务")
            self.execute_sign_task()
            # 签到后等待3-5秒再执行后续任务
            if not STOP_EVENT.is_set():
                sign_wait = random.randint(3, 5)
                logger.info(f"[账号{self.idx}] ⏳ 签到完成，等待{sign_wait}秒...")
                time.sleep(sign_wait)

        # ========== 第二步：执行原有刷任务逻辑 ==========
        for i in range(1, CFG.TASK_LOOP_TIMES + 1):
            if STOP_EVENT.is_set():
                logger.info(f"[账号{self.idx}] 🛑 任务被强制终止")
                break
                
            self.execute_task(i)
            
            if i < CFG.TASK_LOOP_TIMES:
                if STOP_EVENT.is_set(): break
                self._wait_random()
                
        logger.info(f"[账号{self.idx}] 🎉 所有任务完成（签到+刷任务）")

def worker_entry(index: int, data: str):
    try:
        worker = SuKanTaskWorker(index, data)
        worker.run()
    except Exception as e:
        logger.error(f"[账号{index}] ❌ 线程发生严重错误: {e}", exc_info=True)

def main():
    print("\n=================================================")
    print("代码发布地址：https://github.com/YSJohnson/QingLongScripts-YSJ")
    print("=================================================\n")

    if CFG is None:
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    accounts = [line.strip() for line in re.split(r'[\n@]', CFG.SUKAN_URL) if line and line.strip()]
    logger.info(f"检测到 {len(accounts)} 个待处理账号")

    with ThreadPoolExecutor(max_workers=CFG.CONCURRENCY) as executor:
        futures = [executor.submit(worker_entry, i + 1, acc) for i, acc in enumerate(accounts)]
        
        while not STOP_EVENT.is_set():
            if all(f.done() for f in futures):
                break
            time.sleep(0.5)

        for f in futures:
            if f.done() and not f.cancelled():
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"捕获到线程异常: {e}")

    logger.info("✅ 所有账号任务执行完毕（签到+刷任务）")

if __name__ == '__main__':
    main()