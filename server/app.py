# -*- coding: utf-8 -*-
"""
金成峰司机管理 · 企业微信小程序后端 API

启动：
  python app.py            # 默认 8081 端口（与 8080 webhook 区分）

接口：
  登录       POST  /api/login                     {code} 或调试模式 {userid}
  当前用户   GET   /api/me                        校验 token，返回 {userid, name, is_admin, debug_mode}
  基础数据   GET   /api/options                   {vehicles, origins, destinations}
  出车       POST  /api/trips                     {plate, origin, destination, trip_date?}
  加油       POST  /api/refuels                   {refuel_date, odometer, travel_km, oil_price, liters, amount, plate?}
  保养       POST  /api/maintenances              multipart: maintain_time, photo, items, cost, remark, plate?
  报表       GET   /api/reports/trips?from=&to=&group_by=
            GET   /api/reports/refuels?from=&to=&group_by=
            GET   /api/reports/maintenances?from=&to=&group_by=
  汇总       GET   /api/summary?from=&to=       按人/按车辆分组汇总
  导出       GET   /api/export/trips|refuels|maintenances?from=&to=   （返回 .xlsx 文件）
  管理       GET/POST/DELETE /api/admin/vehicles、/api/admin/origins、/api/admin/destinations
  用户管理   GET   /api/admin/users                   用户列表（含三表记录数）
            POST  /api/admin/users                   {userid,name,role?,remark?} 登记新用户
            PATCH /api/admin/users/<userid>          {role|status|name} 改角色/状态/姓名
  同步       GET   /api/sync/status             在线表格同步状态
            POST  /api/sync/push                {kind,id} 手动重推一条记录到在线表格（管理员）
            POST  /api/sync/setup               {force} 初始化/重建同步表（管理员）
  网页       GET   /web                         网页端报表（密码见 config.json web_password）
            POST  /api/web/login                {password, userid?} 网页登录换 token（填 userid 识别身份；系统无管理员时首个带账号登录者自动成为管理员）
  健康       GET   /health
"""
import os
import time
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

import db
import excel_export
import sync_sheet
from auth import (CONFIG, create_session, get_session, jscode_to_userid,
                  require_session, require_admin)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 容器部署时通过环境变量 UPLOAD_DIR 指向挂载卷，如 /data/uploads
UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = CONFIG.get("upload_max_mb", 10) * 1024 * 1024

# 在线表格同步开关：容器部署无 wecom-cli（依赖本机企业微信授权），应设 WX_SYNC_ENABLED=0 关闭
SYNC_ENABLED = os.environ.get("WX_SYNC_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")

# 在线表格同步：提交后异步追加，不阻塞接口响应
_sync_pool = ThreadPoolExecutor(max_workers=2)


def enqueue_sync(kind, rec):
    """异步推送一条记录到在线表格同步表（失败不影响业务，记录在 sync_status.json）"""
    if not SYNC_ENABLED:
        return  # 容器环境同步功能不可用（wecom-cli 无法运行），静默跳过
    try:
        _sync_pool.submit(sync_sheet.sync_record, kind, rec)
    except Exception as e:  # noqa
        sync_sheet.log("入队失败: %s" % e)


# ---------- 工具 ----------
def ok(data=None):
    return jsonify({"ok": True, "data": data or {}})


def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def fnum(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------- 登录 ----------
@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    debug_userid = (body.get("userid") or "").strip()

    if CONFIG.get("debug_mode"):
        uid = debug_userid or "dev001"
    else:
        if not code:
            return fail("缺少 code")
        uid, err = jscode_to_userid(code)
        if err:
            return fail(err, 401)

    token, sess = create_session(uid)
    return ok({
        "token": token,
        "userid": sess["userid"],
        "name": sess["name"],
        "is_admin": sess["is_admin"],
        "debug_mode": CONFIG.get("debug_mode"),
    })


@app.route("/api/me", methods=["GET"])
@require_session
def me(sess):
    return ok({"userid": sess["userid"], "name": sess["name"],
               "is_admin": db.is_admin(sess["userid"]),
               "debug_mode": CONFIG.get("debug_mode")})


# ---------- 基础数据 ----------
@app.route("/api/options", methods=["GET"])
@require_session
def options(sess):
    return ok({
        "vehicles": db.list_vehicles(),
        "origins": db.list_locations("origin"),
        "destinations": db.list_locations("destination"),
    })


# ---------- 出车 ----------
@app.route("/api/trips", methods=["POST"])
@require_session
def add_trip(sess):
    if db.user_disabled(sess["userid"]):
        return fail("账号已被禁用，请联系管理员", 403)
    body = request.get_json(silent=True) or {}
    plate = (body.get("plate") or "").strip()
    origin = (body.get("origin") or "").strip()
    destination = (body.get("destination") or "").strip()
    if not plate or not origin or not destination:
        return fail("车牌号、出发地、目的地均不能为空")
    trip_date = (body.get("trip_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    rid = db.add_trip(sess["userid"], sess["name"], plate, origin, destination, trip_date)
    enqueue_sync("trip", {"id": rid, "name": sess["name"], "plate": plate,
                          "origin": origin, "destination": destination,
                          "trip_date": trip_date})
    return ok({"msg": "出车记录已提交"})


# ---------- 加油 ----------
@app.route("/api/refuels", methods=["POST"])
@require_session
def add_refuel(sess):
    if db.user_disabled(sess["userid"]):
        return fail("账号已被禁用，请联系管理员", 403)
    body = request.get_json(silent=True) or {}
    refuel_date = (body.get("refuel_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    odometer = fnum(body.get("odometer"))
    travel_km = fnum(body.get("travel_km"))
    oil_price = fnum(body.get("oil_price"))
    liters = fnum(body.get("liters"))
    amount = fnum(body.get("amount"))
    plate = (body.get("plate") or "").strip()
    # 油耗：用户填了用用户的，否则按 加油量/行驶公里*100 计算
    fuel_consumption = fnum(body.get("fuel_consumption"))
    if fuel_consumption <= 0 and travel_km > 0 and liters > 0:
        fuel_consumption = round(liters / travel_km * 100, 2)
    if liters <= 0 and amount > 0 and oil_price > 0:
        liters = round(amount / oil_price, 2)
    if amount <= 0 and liters > 0 and oil_price > 0:
        amount = round(liters * oil_price, 2)
    rid = db.add_refuel(sess["userid"], sess["name"], refuel_date, odometer, travel_km,
                        oil_price, liters, amount, fuel_consumption, plate)
    enqueue_sync("refuel", {"id": rid, "name": sess["name"], "plate": plate,
                            "refuel_date": refuel_date, "odometer": odometer,
                            "travel_km": travel_km, "oil_price": oil_price,
                            "liters": liters, "amount": amount,
                            "fuel_consumption": fuel_consumption})
    return ok({"msg": "加油记录已提交"})


# ---------- 保养（照片上传） ----------
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@app.route("/api/maintenances", methods=["POST"])
@require_session
def add_maintenance(sess):
    if db.user_disabled(sess["userid"]):
        return fail("账号已被禁用，请联系管理员", 403)
    maintain_time = (request.form.get("maintain_time") or "").strip() \
        or datetime.now().strftime("%Y-%m-%d %H:%M")
    items = (request.form.get("items") or "").strip()
    remark = (request.form.get("remark") or "").strip()
    plate = (request.form.get("plate") or "").strip()
    cost = fnum(request.form.get("cost"))

    photo_path = ""
    photo = request.files.get("photo")
    if photo and photo.filename:
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            return fail("仅支持图片文件（jpg/png/gif/webp/bmp）")
        fname = "%s_%d%s" % (sess["userid"], int(time.time()), ext)
        photo.save(os.path.join(UPLOAD_DIR, fname))
        photo_path = fname

    rid = db.add_maintenance(sess["userid"], sess["name"], maintain_time, photo_path,
                             items, cost, remark, plate)
    enqueue_sync("maintenance", {"id": rid, "name": sess["name"], "plate": plate,
                                 "maintain_time": maintain_time, "items": items,
                                 "cost": cost, "remark": remark})
    return ok({"msg": "保养记录已提交", "photo": photo_path})


@app.route("/uploads/<fname>")
def serve_upload(fname):
    fname = secure_filename(fname)
    return flask_send(fname)


def flask_send(fname):
    from flask import send_from_directory
    path = os.path.join(UPLOAD_DIR, fname)
    if not os.path.exists(path):
        return fail("文件不存在", 404)
    return send_from_directory(UPLOAD_DIR, fname)


# ---------- 报表 ----------
@app.route("/api/reports/trips", methods=["GET"])
@require_session
def rpt_trips(sess):
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    group_by = request.args.get("group_by", "trip_date")
    return ok({
        "summary": {"total": sum(r["cnt"] for r in
                                 db.report_trips(date_from, date_to, group_by))},
        "group": db.report_trips(date_from, date_to, group_by),
        "detail": db.report_trips_detail(date_from, date_to),
    })


@app.route("/api/reports/refuels", methods=["GET"])
@require_session
def rpt_refuels(sess):
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    group_by = request.args.get("group_by", "refuel_date")
    return ok({
        "summary": db.report_refuels_summary(date_from, date_to),
        "group": db.report_refuels_by(date_from, date_to, group_by),
        "detail": db.report_refuels_detail(date_from, date_to),
    })


@app.route("/api/reports/maintenances", methods=["GET"])
@require_session
def rpt_maintenances(sess):
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    group_by = request.args.get("group_by", "maintain_time")
    return ok({
        "summary": db.report_maintenances_summary(date_from, date_to),
        "group": db.report_maintenances_by(date_from, date_to, group_by),
        "detail": db.report_maintenances_detail(date_from, date_to),
    })


# ---------- 分组汇总（按人 / 按车辆） ----------
@app.route("/api/summary", methods=["GET"])
@require_session
def summary(sess):
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    return ok({
        "by_person": db.summary_by_person(date_from, date_to),
        "by_vehicle": db.summary_by_vehicle(date_from, date_to),
    })


# ---------- 报表导出 Excel ----------
@app.route("/api/export/<kind>", methods=["GET"])
@require_session
def export_report(sess, kind):
    if kind not in excel_export.EXPORTERS:
        return fail("不支持的导出类型: %s" % kind)
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    data, fname = excel_export.EXPORTERS[kind](date_from, date_to)
    from flask import send_file
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=fname,
    )


# ---------- 管理员：车辆 ----------
@app.route("/api/admin/vehicles", methods=["GET"])
@require_admin
def adm_vehicles_get(sess):
    return ok({"vehicles": db.list_vehicles()})


@app.route("/api/admin/vehicles", methods=["POST"])
@require_admin
def adm_vehicles_post(sess):
    body = request.get_json(silent=True) or {}
    err = db.add_vehicle(body.get("plate", ""))
    return (ok({"msg": "已添加"}) if not err else fail(err))


@app.route("/api/admin/vehicles", methods=["DELETE"])
@require_admin
def adm_vehicles_del(sess):
    body = request.get_json(silent=True) or {}
    ok_flag = db.delete_vehicle(body.get("plate", ""))
    return ok({"msg": "已删除" if ok_flag else "未找到该车牌号"})


# ---------- 管理员：地点 ----------
@app.route("/api/admin/locations", methods=["GET"])
@require_admin
def adm_locations_get(sess):
    return ok({"origins": db.list_locations("origin"),
               "destinations": db.list_locations("destination")})


@app.route("/api/admin/locations", methods=["POST"])
@require_admin
def adm_locations_post(sess):
    body = request.get_json(silent=True) or {}
    err = db.add_location(body.get("name", ""), body.get("kind", "origin"))
    return (ok({"msg": "已添加"}) if not err else fail(err))


@app.route("/api/admin/locations", methods=["DELETE"])
@require_admin
def adm_locations_del(sess):
    body = request.get_json(silent=True) or {}
    ok_flag = db.delete_location(body.get("name", ""), body.get("kind", "origin"))
    return ok({"msg": "已删除" if ok_flag else "未找到该地点"})


# ---------- 管理员：用户管理 ----------
@app.route("/api/admin/users", methods=["GET"])
@require_admin
def adm_users_get(sess):
    users = db.list_users()
    return ok({"users": users, "admin_count": db.count_admins(), "total": len(users)})


@app.route("/api/admin/users", methods=["POST"])
@require_admin
def adm_users_post(sess):
    body = request.get_json(silent=True) or {}
    err = db.add_user(body.get("userid", ""), body.get("name", ""),
                      body.get("role", "user"), body.get("remark", ""))
    return (ok({"msg": "已添加"}) if not err else fail(err))


@app.route("/api/admin/users/<uid>", methods=["PATCH"])
@require_admin
def adm_users_patch(sess, uid):
    """修改用户角色/状态/姓名。body: {role|status|name}"""
    body = request.get_json(silent=True) or {}
    role = body.get("role")
    status = body.get("status")
    name = body.get("name")
    if not db.get_user(uid):
        return fail("用户不存在: %s" % uid, 404)
    # 自我保护：不能取消自己的管理员身份、不能禁用自己
    if uid == sess["userid"]:
        if role == "user":
            return fail("不能取消自己的管理员身份", 400)
        if status == "disabled":
            return fail("不能禁用自己", 400)
    # 最后一位管理员保护
    if role == "user" and db.is_admin(uid) and db.count_admins() <= 1:
        return fail("系统至少需要保留一名管理员", 400)
    err = None
    if err is None and role is not None:
        err = db.set_user_role(uid, role)
    if err is None and status is not None:
        err = db.set_user_status(uid, status)
    if err is None and name is not None:
        err = db.set_user_name(uid, name)
    return (ok({"msg": "已更新"}) if err is None else fail(err))


# ---------- 网页端报表 ----------
@app.route("/web", methods=["GET"])
def web_page():
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE_DIR, "web"), "index.html")


@app.route("/api/web/login", methods=["POST"])
def web_login():
    body = request.get_json(silent=True) or {}
    pwd = (body.get("password") or "").strip()
    expected = CONFIG.get("web_password", "")
    if not expected:
        return fail("服务端未配置 web_password，无法使用网页端", 500)
    if pwd != expected:
        return fail("密码错误", 401)
    uid = (body.get("userid") or "").strip() or "web"
    if uid != "web":
        # 系统无管理员时，首个在网页端带账号登录的人自动成为管理员
        db.maybe_first_admin(uid)
    token, sess = create_session(uid)
    return ok({"token": token, "userid": uid, "name": sess["name"],
               "is_admin": sess["is_admin"]})


# ---------- 在线表格同步状态 ----------
KIND_TABLE = {"trip": ("trips", "id"), "refuel": ("refuels", "id"),
              "maintenance": ("maintenances", "id")}


@app.route("/api/sync/status", methods=["GET"])
@require_session
def sync_status(sess):
    st = sync_sheet.get_status()
    if not SYNC_ENABLED:
        st["enabled"] = False
        st["ready"] = False
        st["reason"] = "当前环境未启用在线表格同步（容器部署不支持 wecom-cli）"
    else:
        st["enabled"] = True
    return ok(st)


@app.route("/api/sync/push", methods=["POST"])
@require_admin
def sync_push(sess):
    """手动重推某条记录到在线表格。body: {kind: trip/refuel/maintenance, id: N}"""
    body = request.get_json(silent=True) or {}
    kind = (body.get("kind") or "").strip()
    rid = body.get("id")
    if kind not in KIND_TABLE:
        return fail("kind 必须是 trip/refuel/maintenance")
    table, _ = KIND_TABLE[kind]
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM %s WHERE id = ?" % table, (rid,)).fetchone()
    conn.close()
    if not row:
        return fail("记录不存在: %s #%s" % (kind, rid))
    ok_flag, msg = sync_sheet.sync_record(kind, dict(row))
    return (ok({"msg": "已同步到在线表格"}) if ok_flag
            else fail("同步失败: %s" % msg, 502))


@app.route("/api/sync/setup", methods=["POST"])
@require_admin
def sync_setup(sess):
    """（重新）初始化在线表格同步表。body: {force: true} 强制重建"""
    body = request.get_json(silent=True) or {}
    ok_flag, docid, url, sheet_ids = sync_sheet.setup_sync_sheet(force=bool(body.get("force")))
    if not ok_flag:
        return fail("初始化同步表失败，详见 server/sync.log", 502)
    return ok({"docid": docid, "url": url, "sheet_ids": sheet_ids})


# ---------- 健康检查 ----------
@app.route("/health", methods=["GET"])
def health():
    return "ok"


# ---------- 启动初始化（python app.py 与 gunicorn 加载均会执行） ----------
db.init_db()
# 把 config.json / 环境变量 WX_ADMIN_USERIDS 的 admin_userids 种子化为管理员（覆盖已有角色，保证硬配置生效）
db.ensure_admin_seed(CONFIG.get("admin_userids", []))


if __name__ == "__main__":
    port = CONFIG.get("listen_port", 8081)
    print(f"金成峰司机管理 API 启动: http://127.0.0.1:{port}/health")
    print(f"调试模式: {'开（直接传 userid 登录）' if CONFIG.get('debug_mode') else '关（走企业微信 jscode2session）'}")
    print(f"在线表格同步: {'开' if SYNC_ENABLED else '关（容器环境）'}")
    print(f"数据库: {db.DB_PATH}")
    print(f"上传目录: {UPLOAD_DIR}")
    app.run(host="0.0.0.0", port=port, debug=False)
