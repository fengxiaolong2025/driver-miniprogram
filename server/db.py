# -*- coding: utf-8 -*-
"""
SQLite 数据层：车辆 / 地点 / 出车 / 加油 / 保养 + 报表聚合查询
"""
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 容器部署（腾讯云 CloudBase 云托管）时通过环境变量 DB_PATH 指向挂载卷，如 /data/driver.db
DB_PATH = os.environ.get("DB_PATH") or os.path.join(BASE_DIR, "driver.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'origin',  -- origin 出发地 | destination 目的地
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid TEXT NOT NULL,
    name TEXT NOT NULL,
    plate TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    trip_date TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS refuels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid TEXT NOT NULL,
    name TEXT NOT NULL,
    refuel_date TEXT NOT NULL,
    odometer REAL DEFAULT 0,        -- 公里数（当前里程）
    travel_km REAL DEFAULT 0,       -- 行驶公里
    oil_price REAL DEFAULT 0,       -- 油价（元/升）
    liters REAL DEFAULT 0,          -- 加油量（升）
    amount REAL DEFAULT 0,          -- 金额（元）
    fuel_consumption REAL DEFAULT 0,-- 油耗（升/百公里，自动计算）
    plate TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS maintenances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid TEXT NOT NULL,
    name TEXT NOT NULL,
    maintain_time TEXT NOT NULL,
    photo TEXT DEFAULT '',          -- 照片相对路径
    items TEXT DEFAULT '',          -- 保养项目
    cost REAL DEFAULT 0,            -- 费用（元）
    remark TEXT DEFAULT '',
    plate TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS users (
    userid TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',      -- admin 管理员 | user 普通用户
    status TEXT NOT NULL DEFAULT 'active',  -- active 正常 | disabled 已禁用
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    last_login_at TEXT DEFAULT '',
    remark TEXT DEFAULT ''
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # 并发读写优化（单实例部署）
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ---------- 车辆 ----------
def list_vehicles():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM vehicles ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_vehicle(plate):
    plate = plate.strip()
    if not plate:
        return "车牌号不能为空"
    conn = get_conn()
    try:
        conn.execute("INSERT INTO vehicles (plate) VALUES (?)", (plate,))
        conn.commit()
        return None
    except sqlite3.IntegrityError:
        return "车牌号已存在"
    finally:
        conn.close()


def delete_vehicle(plate):
    conn = get_conn()
    cur = conn.execute("DELETE FROM vehicles WHERE plate = ?", (plate,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------- 地点 ----------
def list_locations(kind=None):
    conn = get_conn()
    if kind:
        rows = conn.execute("SELECT * FROM locations WHERE kind = ? ORDER BY id",
                            (kind,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM locations ORDER BY kind, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_location(name, kind):
    name = name.strip()
    if not name:
        return "地点名称不能为空"
    if kind not in ("origin", "destination"):
        return "地点类型错误"
    conn = get_conn()
    try:
        conn.execute("INSERT INTO locations (name, kind) VALUES (?, ?)", (name, kind))
        conn.commit()
        return None
    except sqlite3.IntegrityError:
        return "该地点已存在"
    finally:
        conn.close()


def delete_location(name, kind):
    conn = get_conn()
    cur = conn.execute("DELETE FROM locations WHERE name = ? AND kind = ?", (name, kind))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------- 出车 ----------
def add_trip(userid, name, plate, origin, destination, trip_date):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO trips (userid, name, plate, origin, destination, trip_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (userid, name, plate, origin, destination, trip_date),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


# ---------- 加油 ----------
def add_refuel(userid, name, refuel_date, odometer, travel_km, oil_price,
               liters, amount, fuel_consumption, plate=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO refuels (userid, name, refuel_date, odometer, travel_km, "
        "oil_price, liters, amount, fuel_consumption, plate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (userid, name, refuel_date, odometer, travel_km, oil_price,
         liters, amount, fuel_consumption, plate),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


# ---------- 保养 ----------
def add_maintenance(userid, name, maintain_time, photo, items, cost, remark, plate=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO maintenances (userid, name, maintain_time, photo, items, cost, remark, plate) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (userid, name, maintain_time, photo, items, cost, remark, plate),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


# ---------- 报表 ----------
def report_trips(date_from="", date_to="", group_by="trip_date"):
    """出车报表：按分组维度统计出车次数。group_by: trip_date/name/plate/origin/destination"""
    dims = {"trip_date": "trip_date", "name": "name", "plate": "plate",
            "origin": "origin", "destination": "destination"}
    key = dims.get(group_by, "trip_date")
    conds, params = [], []
    if date_from:
        conds.append("trip_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("trip_date <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = (f"SELECT {key} AS dim_key, COUNT(*) AS cnt "
           f"FROM trips{where} GROUP BY {key} ORDER BY cnt DESC")
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def report_trips_detail(date_from="", date_to=""):
    """出车明细（最新在前）。"""
    conds, params = [], []
    if date_from:
        conds.append("trip_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("trip_date <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"SELECT * FROM trips{where} ORDER BY trip_date DESC, id DESC LIMIT 500"
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def report_refuels_summary(date_from="", date_to=""):
    """加油汇总：总次数/总金额/总升数/平均油价/平均油耗。"""
    conds, params = [], []
    if date_from:
        conds.append("refuel_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("refuel_date <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = (f"SELECT COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS total_amount, "
           f"COALESCE(SUM(liters),0) AS total_liters, "
           f"COALESCE(AVG(CASE WHEN oil_price>0 THEN oil_price END),0) AS avg_price, "
           f"COALESCE(AVG(CASE WHEN fuel_consumption>0 THEN fuel_consumption END),0) AS avg_fuel "
           f"FROM refuels{where}")
    conn = get_conn()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row)


def report_refuels_by(date_from="", date_to="", group_by="refuel_date"):
    """加油分组统计：次数/金额/升数。group_by: refuel_date/name/plate"""
    dims = {"refuel_date": "refuel_date", "name": "name", "plate": "plate"}
    key = dims.get(group_by, "refuel_date")
    conds, params = [], []
    if date_from:
        conds.append("refuel_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("refuel_date <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = (f"SELECT {key} AS dim_key, COUNT(*) AS cnt, "
           f"COALESCE(SUM(amount),0) AS total_amount, COALESCE(SUM(liters),0) AS total_liters "
           f"FROM refuels{where} GROUP BY {key} ORDER BY cnt DESC")
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def report_refuels_detail(date_from="", date_to=""):
    conds, params = [], []
    if date_from:
        conds.append("refuel_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("refuel_date <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"SELECT * FROM refuels{where} ORDER BY refuel_date DESC, id DESC LIMIT 500"
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def report_maintenances_detail(date_from="", date_to=""):
    conds, params = [], []
    if date_from:
        conds.append("maintain_time >= ?")
        params.append(date_from)
    if date_to:
        conds.append("maintain_time <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"SELECT * FROM maintenances{where} ORDER BY maintain_time DESC, id DESC LIMIT 500"
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def report_maintenances_by(date_from="", date_to="", group_by="maintain_time"):
    dims = {"maintain_time": "substr(maintain_time,1,10)", "name": "name", "plate": "plate"}
    key = dims.get(group_by, "maintain_time")
    conds, params = [], []
    if date_from:
        conds.append("maintain_time >= ?")
        params.append(date_from)
    if date_to:
        conds.append("maintain_time <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = (f"SELECT {key} AS dim_key, COUNT(*) AS cnt, "
           f"COALESCE(SUM(cost),0) AS total_cost "
           f"FROM maintenances{where} GROUP BY {key} ORDER BY cnt DESC")
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def report_maintenances_summary(date_from="", date_to=""):
    conds, params = [], []
    if date_from:
        conds.append("maintain_time >= ?")
        params.append(date_from)
    if date_to:
        conds.append("maintain_time <= ?")
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    sql = (f"SELECT COUNT(*) AS cnt, COALESCE(SUM(cost),0) AS total_cost "
           f"FROM maintenances{where}")
    conn = get_conn()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return dict(row)


# ---------- 分组汇总（按人 / 按车辆） ----------
def _summary_cond(kind, date_from, date_to):
    """按表类型生成日期过滤条件。kind: trip/refuel/maintenance"""
    col = {"trip": "trip_date", "refuel": "refuel_date",
           "maintenance": "maintain_time"}[kind]
    conds, params = [], []
    if date_from:
        conds.append("%s >= ?" % col)
        params.append(date_from)
    if date_to:
        conds.append("%s <= ?" % col)
        params.append(date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def summary_by_person(date_from="", date_to=""):
    """按人汇总：合并出车/加油/保养，按记录总数降序。"""
    trips = {}
    conn = get_conn()
    where, params = _summary_cond("trip", date_from, date_to)
    for r in conn.execute("SELECT name, COUNT(*) cnt FROM trips%s GROUP BY name" % where, params):
        trips[r["name"]] = r["cnt"]
    refuels = {}
    where, params = _summary_cond("refuel", date_from, date_to)
    for r in conn.execute("SELECT name, COUNT(*) cnt, COALESCE(SUM(amount),0) amt "
                          "FROM refuels%s GROUP BY name" % where, params):
        refuels[r["name"]] = (r["cnt"], r["amt"])
    maints = {}
    where, params = _summary_cond("maintenance", date_from, date_to)
    for r in conn.execute("SELECT name, COUNT(*) cnt, COALESCE(SUM(cost),0) cost "
                          "FROM maintenances%s GROUP BY name" % where, params):
        maints[r["name"]] = (r["cnt"], r["cost"])
    conn.close()

    out = []
    for name in set(trips) | set(refuels) | set(maints):
        t = trips.get(name, 0)
        rf = refuels.get(name, (0, 0))
        mt = maints.get(name, (0, 0))
        out.append({
            "name": name,
            "trip_cnt": t,
            "refuel_cnt": rf[0],
            "refuel_amount": round(rf[1], 2),
            "maintain_cnt": mt[0],
            "maintain_cost": round(mt[1], 2),
            "total": t + rf[0] + mt[0],
        })
    out.sort(key=lambda x: (-x["total"], x["name"]))
    return out


def summary_by_vehicle(date_from="", date_to=""):
    """按车辆汇总：合并出车/加油/保养，按记录总数降序（空车牌不计入）。"""
    trips = {}
    conn = get_conn()
    where, params = _summary_cond("trip", date_from, date_to)
    for r in conn.execute("SELECT plate, COUNT(*) cnt FROM trips%s GROUP BY plate" % where, params):
        trips[r["plate"]] = r["cnt"]
    refuels = {}
    where, params = _summary_cond("refuel", date_from, date_to)
    extra = " AND plate != ''" if where else " WHERE plate != ''"
    for r in conn.execute("SELECT plate, COUNT(*) cnt, COALESCE(SUM(amount),0) amt, "
                          "COALESCE(SUM(liters),0) lit FROM refuels%s%s GROUP BY plate"
                          % (where, extra), params):
        refuels[r["plate"]] = (r["cnt"], r["amt"], r["lit"])
    maints = {}
    where, params = _summary_cond("maintenance", date_from, date_to)
    extra = " AND plate != ''" if where else " WHERE plate != ''"
    for r in conn.execute("SELECT plate, COUNT(*) cnt, COALESCE(SUM(cost),0) cost "
                          "FROM maintenances%s%s GROUP BY plate" % (where, extra), params):
        maints[r["plate"]] = (r["cnt"], r["cost"])
    conn.close()

    out = []
    for plate in set(trips) | set(refuels) | set(maints):
        if not plate:
            continue
        t = trips.get(plate, 0)
        rf = refuels.get(plate, (0, 0, 0))
        mt = maints.get(plate, (0, 0))
        out.append({
            "plate": plate,
            "trip_cnt": t,
            "refuel_cnt": rf[0],
            "refuel_amount": round(rf[1], 2),
            "refuel_liters": round(rf[2], 2),
            "maintain_cnt": mt[0],
            "maintain_cost": round(mt[1], 2),
            "total": t + rf[0] + mt[0],
        })
    out.sort(key=lambda x: (-x["total"], x["plate"]))
    return out


# ---------- 用户管理 ----------
def upsert_user(userid, name):
    """登录登记：已存在则更新姓名/最后登录时间；不存在则插入（默认普通用户）。返回用户信息。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
    if row:
        conn.execute("UPDATE users SET name = ?, last_login_at = ? WHERE userid = ?",
                     (name or userid, now, userid))
        role, status, created_at = row["role"], row["status"], row["created_at"]
    else:
        role, status, created_at = "user", "active", now
        conn.execute("INSERT INTO users (userid, name, role, status, created_at, last_login_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)",
                     (userid, name or userid, role, status, created_at, now))
    conn.commit()
    conn.close()
    return {"userid": userid, "name": name or userid, "role": role, "status": status,
            "created_at": created_at, "last_login_at": now}


def maybe_first_admin(userid):
    """系统无任何管理员时，将指定用户置为管理员（网页端首个登录的管理员激活机制）。"""
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()
    if row["c"] > 0:
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO users (userid, name, role, status, created_at, last_login_at) "
                 "VALUES (?, ?, 'admin', 'active', ?, ?) "
                 "ON CONFLICT(userid) DO UPDATE SET role = 'admin'",
                 (userid, userid, now, now))
    conn.commit()
    conn.close()
    return True


def ensure_admin_seed(admin_userids):
    """把 config.json 的 admin_userids 种子化为管理员（启动时调用，覆盖已有角色）。"""
    for uid in (admin_userids or []):
        uid = str(uid).strip()
        if not uid:
            continue
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_conn()
        conn.execute("INSERT INTO users (userid, name, role, status, created_at, last_login_at) "
                     "VALUES (?, ?, 'admin', 'active', ?, ?) "
                     "ON CONFLICT(userid) DO UPDATE SET role = 'admin'",
                     (uid, uid, now, now))
        conn.commit()
        conn.close()


def list_users():
    """用户列表（含三表记录数），管理员在前。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT u.*, "
        "(SELECT COUNT(*) FROM trips t WHERE t.userid = u.userid) AS trip_cnt, "
        "(SELECT COUNT(*) FROM refuels r WHERE r.userid = u.userid) AS refuel_cnt, "
        "(SELECT COUNT(*) FROM maintenances m WHERE m.userid = u.userid) AS maintain_cnt "
        "FROM users u ORDER BY (u.role = 'admin') DESC, u.created_at DESC, u.userid"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user(userid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE userid = ?", (userid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_user(userid, name, role="user", remark=""):
    """管理员手动登记用户。成功返回 None，失败返回错误信息。"""
    userid = (userid or "").strip()
    name = (name or "").strip() or userid
    if not userid:
        return "账号(userid)不能为空"
    if role not in ("admin", "user"):
        return "角色必须是 admin 或 user"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    try:
        conn.execute("INSERT INTO users (userid, name, role, status, created_at, last_login_at, remark) "
                     "VALUES (?, ?, ?, 'active', ?, '', ?)",
                     (userid, name, role, now, remark))
        conn.commit()
        return None
    except sqlite3.IntegrityError:
        return "该账号已存在"
    finally:
        conn.close()


def set_user_role(userid, role):
    if role not in ("admin", "user"):
        return "角色必须是 admin 或 user"
    conn = get_conn()
    cur = conn.execute("UPDATE users SET role = ? WHERE userid = ?", (role, userid))
    conn.commit()
    conn.close()
    return None if cur.rowcount else "用户不存在"


def set_user_status(userid, status):
    if status not in ("active", "disabled"):
        return "状态必须是 active 或 disabled"
    conn = get_conn()
    cur = conn.execute("UPDATE users SET status = ? WHERE userid = ?", (status, userid))
    conn.commit()
    conn.close()
    return None if cur.rowcount else "用户不存在"


def set_user_name(userid, name):
    name = (name or "").strip()
    if not name:
        return "姓名不能为空"
    conn = get_conn()
    cur = conn.execute("UPDATE users SET name = ? WHERE userid = ?", (name, userid))
    conn.commit()
    conn.close()
    return None if cur.rowcount else "用户不存在"


def is_admin(userid):
    conn = get_conn()
    row = conn.execute("SELECT role FROM users WHERE userid = ?", (userid,)).fetchone()
    conn.close()
    return bool(row and row["role"] == "admin")


def user_disabled(userid):
    conn = get_conn()
    row = conn.execute("SELECT status FROM users WHERE userid = ?", (userid,)).fetchone()
    conn.close()
    return bool(row and row["status"] == "disabled")


def count_admins():
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = 'admin'").fetchone()
    conn.close()
    return row["c"]


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成:", DB_PATH)
