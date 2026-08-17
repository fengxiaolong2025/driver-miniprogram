# -*- coding: utf-8 -*-
"""
企业微信小程序登录与鉴权

登录流程：
  小程序 wx.qy.login() 取 code → POST /api/login → 后端调企业微信
  jscode2session 换 userid → 生成会话 token 返回。

调试模式（config.json debug_mode=true）：
  前端直接传 userid 即可登录，不依赖企业微信后台，方便本地联调。
"""
import json
import os
import secrets
import time
import urllib.request
import urllib.parse
import urllib.error

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "corpid": "",            # 企业 ID（ww 开头）
    "secret": "",            # 企业微信小程序 secret（管理后台 → 小程序 → 查看）
    "admin_userids": [],     # 管理员 userid 列表，如 ["ZhangSan"]
    "debug_mode": True,      # True=调试登录（传 userid 即可），False=走企业微信 jscode2session
    "listen_port": 8081,
    "upload_max_mb": 10,     # 保养照片大小上限
}


def _env_flag(key, default):
    """环境变量布尔值解析：1/true/yes/on → True"""
    v = os.environ.get(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_config():
    """加载 config.json，并用环境变量覆盖（容器部署优先用环境变量注入密钥）。"""
    cfg = {**DEFAULT_CONFIG}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    # ---- 环境变量覆盖（云托管部署时无需修改 config.json）----
    if os.environ.get("WX_CORPID"):
        cfg["corpid"] = os.environ["WX_CORPID"].strip()
    if os.environ.get("WX_SECRET"):
        cfg["secret"] = os.environ["WX_SECRET"].strip()
    if os.environ.get("WX_ADMIN_USERIDS"):
        cfg["admin_userids"] = [u.strip() for u in
                                os.environ["WX_ADMIN_USERIDS"].split(",") if u.strip()]
    if os.environ.get("WX_DEBUG_MODE"):
        cfg["debug_mode"] = _env_flag("WX_DEBUG_MODE", cfg.get("debug_mode", True))
    if os.environ.get("WX_WEB_PASSWORD"):
        cfg["web_password"] = os.environ["WX_WEB_PASSWORD"].strip()
    if os.environ.get("WX_PORT"):
        try:
            cfg["listen_port"] = int(os.environ["WX_PORT"])
        except ValueError:
            pass
    if os.environ.get("WX_UPLOAD_MAX_MB"):
        try:
            cfg["upload_max_mb"] = int(os.environ["WX_UPLOAD_MAX_MB"])
        except ValueError:
            pass
    return cfg


CONFIG = load_config()


# ---------- 企业微信 access_token（缓存） ----------
_token = None
_token_expires = 0


def get_access_token():
    global _token, _token_expires
    if _token and time.time() < _token_expires - 300:
        return _token
    if not CONFIG.get("corpid") or not CONFIG.get("secret"):
        return None
    url = ("https://qyapi.weixin.qq.com/cgi-bin/gettoken"
           "?corpid=%s&corpsecret=%s" % (CONFIG["corpid"], CONFIG["secret"]))
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("errcode"):
            return None
        _token = data["access_token"]
        _token_expires = time.time() + data.get("expires_in", 7200)
        return _token
    except Exception:
        return None


def jscode_to_userid(code):
    """企业微信小程序 code 换 userid。"""
    token = get_access_token()
    if not token:
        return None, "无法获取 access_token，请检查 corpid/secret 配置"
    url = ("https://qyapi.weixin.qq.com/cgi-bin/miniprogram/jscode2session"
           "?access_token=%s&js_code=%s&grant_type=authorization_code"
           % (token, urllib.parse.quote(code)))
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("errcode"):
            return None, "登录失败: %s (%s)" % (data.get("errmsg"), data.get("errcode"))
        userid = data.get("userid") or data.get("openid", "")
        if not userid:
            return None, "登录响应缺少 userid"
        return userid, None
    except Exception as e:
        return None, "请求 jscode2session 异常: %s" % e


# ---------- 姓名查询（通讯录 API，带缓存） ----------
_user_name_cache = {}


def get_user_name(userid):
    if not userid:
        return userid
    if userid in _user_name_cache:
        return _user_name_cache[userid]
    token = get_access_token()
    if not token:
        _user_name_cache[userid] = userid
        return userid
    url = ("https://qyapi.weixin.qq.com/cgi-bin/user/get"
           "?access_token=%s&userid=%s" % (token, urllib.parse.quote(userid)))
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        name = data.get("name") or userid
        _user_name_cache[userid] = name
        return name
    except Exception:
        _user_name_cache[userid] = userid
        return userid


# ---------- 会话 token ----------
_sessions = {}  # token -> {userid, name, is_admin, created_at}


def create_session(userid):
    """创建会话并返回 token。登录时自动登记用户到 users 表。"""
    if userid == "web":
        # 网页端游客会话（未填账号）：只读报表，无管理权限
        token = secrets.token_hex(16)
        _sessions[token] = {
            "userid": "web",
            "name": "网页报表",
            "is_admin": False,
            "created_at": time.time(),
        }
        return token, _sessions[token]

    name = get_user_name(userid)
    user = db.upsert_user(userid, name)
    token = secrets.token_hex(16)
    _sessions[token] = {
        "userid": userid,
        "name": user["name"],
        "is_admin": user["role"] == "admin",
        "created_at": time.time(),
    }
    return token, _sessions[token]


def get_session(token):
    return _sessions.get(token)


def require_session(func):
    """Flask 装饰器：校验 Authorization: Bearer <token>。"""
    from functools import wraps
    from flask import request, jsonify

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        sess = get_session(token)
        if not sess:
            return jsonify({"error": "未登录或会话已过期"}), 401
        return func(sess, *args, **kwargs)

    return wrapper


def require_admin(func):
    """Flask 装饰器：管理员才能访问（实时查库，角色变更立即生效）。"""
    from functools import wraps
    from flask import request, jsonify

    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        sess = get_session(token)
        if not sess:
            return jsonify({"error": "未登录或会话已过期"}), 401
        if not db.is_admin(sess["userid"]):
            return jsonify({"error": "无管理员权限"}), 403
        return func(sess, *args, **kwargs)

    return wrapper
