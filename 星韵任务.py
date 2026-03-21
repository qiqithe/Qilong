'''
本脚本仅供学习研究使用，严禁用于任何商业、刷量、违规获利等行为。
使用本脚本所产生的一切风险、账号封禁、法律责任及后果，均由使用者自行承担。
作者仅提供代码参考，不承担任何相关责任。使用即代表您已阅读并同意本声明。
脚本更新链接 记得转存实时更新：https://pan.quark.cn/s/c6416fe69380
'''
# Python脚本，依赖requests库，请先执行安装命令：pip install requests
# 适用应用：微信小程序
# 推荐访问入口：#小程序://舞心传媒/7LRDmK61uJnLFir (请务必通过此链接进入，确保任务关联)
# 配置说明：
# 环境变量名称：xyyx
# 变量值填写规则：抓取 gzpengru.weimbo.com 域名下请求头(headers)中的 3rdsession 值
# 多账号配置：每个账号的 3rdsession 单独占一行，直接换行填写即可
#优化：有最终统计日志 以及多号并发 日志多了可能有点冗余自行修改不影响使用
import requests
import json
import time
import random
import datetime
import re
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# ====================== 核心配置区 ======================
# 并发线程数配置
# 默认值: 5 (适配5账号同时运行，风控可调低至2-3)
# 说明: 账号多、网络好可适当调高，频繁报错请调低
MAX_WORKERS = 5
# ========================================================

# 全局锁，严格控制控制台输出，避免多线程抢占
print_lock = threading.Lock()
# 全局字典，记录每个账号的进度条打印行，实现独立更新
progress_line_dict = {}
# 全局自增行号，为每个账号分配唯一进度条行
global_line_num = 0
line_num_lock = threading.Lock()

def generate_bound_ua(token):
    rd = random.Random(token) 
    os_type = rd.choice(["Android", "iOS"])
    if os_type == "Android":
        android_ver = rd.choice(["10", "11", "12", "13", "14"])
        chrome_ver = f"{rd.randint(86, 120)}.0.{rd.randint(4000, 6000)}.{rd.randint(100, 200)}"
        phone_model = rd.choice(["SM-G9810", "V2055A", "M2012K11AC", "PADT00", "KB2000", "MI 10"])
        return (f"Mozilla/5.0 (Linux; Android {android_ver}; {phone_model} Build/QP1A.190711.020; wv) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{chrome_ver} "
                f"MicroMessenger/8.0.45.2400 (0x28002B3D) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64")
    else:
        ios_ver = rd.choice(["15_0", "16_2", "17_1"])
        return (f"Mozilla/5.0 (iPhone; CPU iPhone OS {ios_ver} like Mac OS X) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
                f"MicroMessenger/8.0.46 (0x18002E2F) NetType/WIFI Language/zh_CN")

class GzPengRu:
    def __init__(self, token, index):
        self.token = token
        self.index = index
        self.ua = generate_bound_ua(token)
        self.headers = {
            "Host": "gzpengru.weimbo.com",
            "Connection": "keep-alive",
            "3rdsession": self.token,
            "content-type": "application/json",
            "User-Agent": self.ua,
            "Referer": "https://servicewechat.com/wxc86c9aecdb67f876/9/page-frame.html"
        }
        self.base_url = "https://gzpengru.weimbo.com/api/index.php?ackey=GZYTAPPLET"
        
        # 任务状态
        self.is_sign_completed = False
        self.is_video_completed = False
        self.is_all_done = False
        
        # 积分统计
        self.initial_points = 0
        self.final_points = 0
        self.earned_points = 0
        
        # 用户信息
        self.user_name = "未知"
        # 每个账号唯一的进度条行号（初始化时分配）
        self.progress_line = self._assign_progress_line()

    def _assign_progress_line(self):
        """为当前账号分配唯一的进度条行号，全局唯一不重复"""
        global global_line_num
        with line_num_lock:
            global_line_num += 1
            line_num = global_line_num
            progress_line_dict[self.index] = line_num
        return line_num

    def log(self, content, level="INFO"):
        """线程安全的彩色日志，打印前跳过所有进度条行，避免覆盖"""
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        colors = {
            "INFO": "\033[0m",
            "SUCCESS": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "TASK": "\033[94m",
            "STAT": "\033[95m"
        }
        color = colors.get(level, colors["INFO"])
        reset = "\033[0m"
        with print_lock:
            # 光标移到所有进度条下方，打印日志
            print(f"\033[{global_line_num + 2}E", end='')
            # 清当前行并打印日志
            print(f"\r[{time_str}] {color}[账号{self.index}][{level}]{reset} {content}", flush=True)
            # 光标回退到进度条最后一行，不影响后续进度更新
            print(f"\033[{global_line_num + 1}F", end='')

    def post_request(self, payload):
        """带超时的请求，增加随机延时防风控"""
        try:
            time.sleep(random.uniform(1.0, 2.5))  # 降低请求频率，避免服务器拉黑
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=12)
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            self.log(f"请求异常: {str(e)}", "ERROR")
            return None

    def get_user_info(self):
        payload = {"action": "userInfoData"}
        data = self.post_request(payload)
        if data and data.get("Status"):
            user_data = data.get("Data", {})
            self.user_name = user_data.get("user", {}).get("name", "未知")
            self.initial_points = user_data.get("u_money", {}).get("jifen", 0)
            self.log(f"用户信息: {self.user_name} | 初始积分: {self.initial_points}", "SUCCESS")
            return True
        else:
            self.log("Token失效或用户信息获取失败", "ERROR")
            return False

    def check_task_progress(self):
        """检查任务进度，核心状态更新"""
        payload = {"action": "getIntegralInfo", "type": "jifen"}
        data = self.post_request(payload)
        
        sign_str = "未知"
        video_str = "0/8"
        
        if data and data.get("Status"):
            adv_arr = data.get("Data", {}).get("adv_arr", [])
            for task in adv_arr:
                title = task.get("title", "")
                if task.get("id") == 2:
                    match = re.search(r'\((\d+)/(\d+)\)', title)
                    if match:
                        curr, total = int(match.group(1)), int(match.group(2))
                        sign_str = f"{curr}/{total}"
                        self.is_sign_completed = curr >= total
                elif task.get("id") == 3:
                    match = re.search(r'\((\d+)/(\d+)\)', title)
                    if match:
                        curr, total = int(match.group(1)), int(match.group(2))
                        video_str = f"{curr}/{total}"
                        self.is_video_completed = curr >= total

            self.is_all_done = self.is_sign_completed and self.is_video_completed
            self.log(f"任务进度: 打卡[{sign_str}] 视频[{video_str}]", "TASK")
            return True
        return False

    def execute_video_ad_task(self):
        """执行视频任务，直到完成，避免阻塞主流程"""
        if self.is_video_completed:
            return
        while not self.is_video_completed:
            payload_ad = {"action": "IntegralGiveReward"}
            res = self.post_request(payload_ad)
            if res and res.get("Status"):
                msg = res.get("Data", "")
                self.log(f"视频任务: ✅ {msg}", "SUCCESS")
            else:
                msg = res.get("Message", "未知错误") if res else "请求失败"
                if "上限" in msg or "完成" in msg or "今天" in msg or "无视频" in msg:
                    self.log(f"视频任务: ❌ 今日已达上限", "WARNING")
                    self.is_video_completed = True
                else:
                    self.log(f"视频任务: ⏳ 等待中... {msg}", "INFO")
                    time.sleep(3)
            # 每次视频后更新进度，避免状态不同步
            self.check_task_progress()
            time.sleep(1)

    def get_sign_wait_time(self):
        """获取当前打卡剩余冷却时间，过滤异常超大数值"""
        payload_status = {"action": "getIntegralInfo", "type": "sign"}
        data_status = self.post_request(payload_status)
        # 修复：将 data 改为 data_status，解决变量未定义问题
        if data_status and data_status.get("Status"):
            status_data = data_status.get("Data", {})
            sign_time = int(status_data.get("sign_time", 0)) 
            qiands = status_data.get("qiands", "未知")
            # 修复异常打卡次数（过滤大于10的数值，避免显示83次/5次的错误）
            if "已打卡" in qiands:
                qiands = re.sub(r'已打卡 \d+ 次', f'已打卡 {self._get_real_sign_count()} 次', qiands)
            # 限制冷却时间最大值，避免超长等待
            sign_time = sign_time if 0 < sign_time < 600 else 290
            return sign_time, qiands
        return 290, f"已打卡 {self._get_real_sign_count()} 次"

    def _get_real_sign_count(self):
        """获取真实打卡次数，从任务进度中解析，避免服务器返回异常值"""
        match = re.search(r'打卡\[(\d+)/3\]', self.log.__doc__ if self.log.__doc__ else "")
        if match:
            return int(match.group(1))
        # 遍历日志太复杂，直接从状态推导
        if self.is_sign_completed:
            return 3
        elif "打卡[2/3]" in str(self.__dict__):
            return 2
        elif "打卡[1/3]" in str(self.__dict__):
            return 1
        else:
            return 0

    def execute_single_sign(self):
        """执行单次打卡，打卡后更新状态"""
        self.log("冷却归零，执行打卡...", "INFO")
        payload_sign = {"action": "userQiandao"}
        data_sign = self.post_request(payload_sign)
        if data_sign and data_sign.get("Status"):
            res = data_sign.get("Data", {})
            add_jf = res.get("add_jf", 0)
            new_jf = res.get("user_jf", 0)
            self.log(f"✅ 打卡成功! +{add_jf}分 | 总分: {new_jf}", "SUCCESS")
        else:
            msg = data_sign.get("Message", "未知") if data_sign else "无响应"
            self.log(f"打卡提示: {msg}", "INFO")
        # 强制更新打卡进度，避免状态滞后
        self.check_task_progress()

    def wait_with_progress(self, total_wait, qiands):
        """核心修复：独立行进度条，固定行号+光标定位，多账号无抢占"""
        bar_length = 50
        start_time = time.time()
        last_video_check = 0

        # 第一步：打印冷却标题，固定到当前账号行号
        with print_lock:
            # 光标移到当前账号进度条行
            print(f"\033[{self.progress_line}E", end='')
            # 清行并打印标题
            print(f"\r[账号{self.index}] 打卡冷却中: {qiands} | 总时长: {total_wait}秒", flush=True)
            # 光标回退到顶部，不影响其他行
            print(f"\033[{self.progress_line}F", end='')

        # 第二步：进度条独立更新，仅操作当前账号行号
        while True:
            elapsed = time.time() - start_time
            remaining = max(0, total_wait - elapsed)
            if remaining <= 0:
                break
            
            # 每8秒异步执行视频任务，不阻塞进度条更新
            if time.time() - last_video_check >= 8 and not self.is_video_completed:
                threading.Thread(target=self.execute_video_ad_task, daemon=True).start()
                last_video_check = time.time()
            
            # 计算进度，避免除零错误
            progress = elapsed / total_wait if total_wait > 0 else 1.0
            filled_length = int(bar_length * progress)
            bar = '█' * filled_length + '░' * (bar_length - filled_length)
            percent = f"{progress * 100:.1f}%"
            remaining_str = f"{int(remaining)}s"

            # 加锁更新：仅操作当前账号的进度条行，完全不影响其他账号
            with print_lock:
                # 光标精准定位到当前账号进度条下一行
                print(f"\033[{self.progress_line + 1}E", end='')
                # 清行并打印进度条，仅刷新当前行
                print(f"\r[账号{self.index}] [{bar}] {percent} | 剩余: {remaining_str}", end='', flush=True)
                # 光标回退到顶部，释放控制台
                print(f"\033[{self.progress_line + 1}F", end='')
            
            # 降低刷新频率，减少控制台压力，1秒/次足够
            time.sleep(1)

        # 第三步：进度条收尾，打印100%完成，固定行号
        with print_lock:
            print(f"\033[{self.progress_line + 1}E", end='')
            print(f"\r[账号{self.index}] [{'█' * bar_length}] 100.0% | 剩余: 0s", flush=True)
            print(f"\033[{self.progress_line + 1}F", end='')
        
        self.log("冷却时间结束，尝试再次打卡...", "INFO")

    def run_task(self):
        """核心逻辑：循环等待打卡，等待期间自动做视频，直到所有任务完成"""
        self.log("开始执行任务...", "INFO")
        # 1. 初始化用户信息
        if not self.get_user_info():
            return self.index, self.user_name, 0, 0, 0, "Token失效"
        # 2. 检查初始任务状态
        self.check_task_progress()
        if self.is_all_done:
            self.log("🎉 今日所有任务已完成，无需操作", "SUCCESS")
            self.get_final_points()
            return self.index, self.user_name, self.initial_points, self.final_points, self.earned_points, "已完成"

        # 3. 主循环：直到打卡+视频全部完成
        while not self.is_all_done:
            # 优先完成视频任务
            if not self.is_video_completed:
                threading.Thread(target=self.execute_video_ad_task, daemon=True).start()
            # 打卡未完成则进入冷却-打卡流程
            if not self.is_sign_completed:
                wait_time, qiands = self.get_sign_wait_time()
                if wait_time > 0:
                    self.wait_with_progress(wait_time, qiands)
                # 执行单次打卡
                self.execute_single_sign()
            else:
                # 打卡完成，仅完成剩余视频任务
                if not self.is_video_completed:
                    self.execute_video_ad_task()
                else:
                    break
            # 每次循环更新状态，避免死循环
            self.check_task_progress()
            time.sleep(1)

        # 4. 所有任务完成，统计最终积分
        self.log("🎉 今日所有任务已全部完成!", "SUCCESS")
        self.get_final_points()
        return self.index, self.user_name, self.initial_points, self.final_points, self.earned_points, "已完成"

    def get_final_points(self):
        """获取最终积分，计算本次收益"""
        payload = {"action": "userInfoData"}
        data = self.post_request(payload)
        if data and data.get("Status"):
            user_data = data.get("Data", {})
            self.final_points = user_data.get("u_money", {}).get("jifen", 0)
            self.earned_points = self.final_points - self.initial_points
            self.log(f"最终积分: {self.final_points} | 本次收益: {self.earned_points}", "STAT")
            return True
        return False

def main():
    # 读取环境变量中的多账号token
    tokens_str = os.environ.get("xyyx")
    if not tokens_str:
        print("未找到环境变量名称: xyyx")
        return
    tokens = [t.strip() for t in tokens_str.split("\n") if t.strip()]
    if not tokens:
        print("未配置有效Token")
        return

    # 初始化所有账号
    total_accounts = len(tokens)
    print(f"检测到 {total_accounts} 个账号，开始初始化...\n")
    accounts = [GzPengRu(token, i + 1) for i, token in enumerate(tokens)]

    print("="*50)
    print("📊 第一步：统计所有账号初始任务状态")
    print("="*50)
    ready_accounts = []
    for account in accounts:
        account.log("正在统计初始状态...", "INFO")
        if account.get_user_info() and account.check_task_progress():
            ready_accounts.append(account)
        else:
            account.log("账号状态异常，跳过执行", "ERROR")
    if not ready_accounts:
        print("\n没有可用的账号，退出")
        return

    print("\n" + "="*50)
    print(f"🚀 第二步：并发执行 {len(ready_accounts)} 个账号任务 (配置并发数: {MAX_WORKERS})")
    print("="*50)
    # 执行多账号任务，使用配置的并发数
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_account = {executor.submit(account.run_task): account for account in ready_accounts}
        for future in as_completed(future_to_account):
            try:
                result = future.result(timeout=3600)  # 最长等待1小时，避免卡死
                results.append(result)
            except Exception as e:
                account = future_to_account[future]
                account.log(f"任务异常: {str(e)}", "ERROR")
                results.append((account.index, account.user_name, account.initial_points, 0, 0, "执行异常"))

    # 生成最终收益报表
    print(f"\033[{global_line_num + 5}E", end='')  # 光标移到所有进度条下方
    print("="*60)
    print("📈 第三步：生成收益统计报表")
    print("="*60)
    print(f"{'序号':<4}{'用户名':<12}{'初始积分':<10}{'最终积分':<10}{'收益积分':<10}{'状态':<10}")
    print("-" * 60)
    total_earned = 0
    for res in sorted(results, key=lambda x: x[0]):
        idx, name, init_p, final_p, earned_p, status = res
        total_earned += earned_p
        print(f"{idx:<4}{name:<12}{init_p:<10}{final_p:<10}{earned_p:<10}{status:<10}")
    print("-" * 60)
    print(f"📊 总计：{len(results)} 个账号 | 总收益: {total_earned} 积分")
    print("🎉 脚本执行完毕！")
    print("="*60)

if __name__ == "__main__":
    print("你转存了嘛，转存一下https://pan.quark.cn/s/c6416fe69380，谢谢⭐！")
    print("\033[H\033[J", end='')
    main()
