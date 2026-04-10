#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 天机馆自动化脚本 (加密版)
# 使用本脚本所产生的一切风险、账号封禁、法律责任及后果，
# 均由使用者自行承担。作者仅提供代码参考，不承担任何相关责任。
# ============================================================

"""
功能：签到、分享商品、观看广告
多号：TOKEN_LIST 内置！ 或 TIANJITOKEN 环境变量（#分隔）
优先使用环境变量，无环境变量时使用内置列表
并发：CONCURRENCY 控制并发数
#小程序://天机观/w7xqgbTsXln13OB
#采用内置token 方便不用青龙即可运行的用户运行
"""

import hashlib, base64, os, sys

# ==================== 用户配置区(可修改) ====================

SHARE_PRODUCT_COUNT = 10
WATCH_AD_COUNT = 50
CONCURRENCY = 2

TOKEN_LIST = [
    "",
]
#上面是内置token运行
# ==================== 以下为加密核心代码 ====================

_PAYLOAD = (
    "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"
    "M1cNeOmPKoalu4lIGO+o3LY="
)

def _r(_x, _y):
    _m = 0
    for _c in _x:
        _m = (_m * 31 + ord(_c)) & 0xFFFFFFFF
    _m = _m ^ sum(ord(_c) * (i + 7) for i, _c in enumerate(_y))
    return _m

def _d(_p):
    _a = [106, 105, 101, 107, 97, 105, 100, 101, 115, 104, 105, 103, 97, 121]
    _b = "".join(chr(_n ^ 0x00) for _n in _a)
    if _p != _b:
        raise ValueError(_r.__name__)
    _k = hashlib.sha256(_p.encode()).digest()
    _v = hashlib.md5(_p.encode()).digest()
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as _pd
    _ct = base64.b64decode(_PAYLOAD)
    _c = Cipher(algorithms.AES(_k), modes.CBC(_v))
    _u = _c.decryptor()
    _raw = _u.update(_ct) + _u.finalize()
    _up = _pd.PKCS7(128).unpadder()
    return (_up.update(_raw) + _up.finalize()).decode()

if __name__ == "__main__":
    _a = [106, 105, 101, 107, 97, 105, 100, 101, 115, 104, 105, 103, 97, 121]
    _k = "".join(chr(_n) for _n in _a)
    try:
        code = _d(_k)
    except Exception:
        print("[FAIL] 解密失败")
        sys.exit(1)
    exec(code, {"__builtins__": __builtins__, "SHARE_PRODUCT_COUNT": SHARE_PRODUCT_COUNT, "WATCH_AD_COUNT": WATCH_AD_COUNT, "CONCURRENCY": CONCURRENCY, "TOKEN_LIST": TOKEN_LIST})
