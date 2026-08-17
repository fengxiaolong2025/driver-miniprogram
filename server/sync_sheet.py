# -*- coding: utf-8 -*-
"""
在线表格自动同步 · 金成峰司机数据同步

原理：wecom-cli sheet rows append 将本库出车/加油/保养记录追加到
企业微信在线表格（机器人自建，三子表：出车记录 / 加油记录 / 保养记录）。

权限说明：wecom-cli 的机器人身份只能写入"机器人创建或拥有的"文档，
无法写真人用户创建的「金成峰司机出车统计」，故同步目标是本模块自动
创建/维护的「金成峰司机数据同步」表；如需改同步到其它表，修改
sync_config.json 中的 docid 与 sheet_ids 即可（该表需由同一机器人创建）。

模块职责：
  setup_sync_sheet()  幂等创建同步表（三子表+表头），仅在配置缺失时执行
  sync_record(kind, rec) 追加一行（kind: trip/refuel/maintenance）
  ensure_ready()      返回是否可用（表已建好）
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "sync_config.json")
LOG_PATH = os.path.join(BASE_DIR, "sync.log")
STATUS_PATH = os.path.join(BASE_DIR, "sync_status.json")
MAX_STATUS = 100

# wecom-cli 可执行文件（升级到 1.1.0+ 后支持 sheet 命令）
WECOM_CLI = r"C:\Users\75720\.workbuddy\binaries\node\cli-connector-packages\wecom-cli.cmd"
if not os.path.exists(WECOM_CLI):
    WECOM_CLI = "wecom-cli"  # 回退到 PATH

DOC_NAME = "金成峰司机数据同步"

# 三个子表：表头（追加行按此列序）
SHEET_DEFS = {
    "trip": {
        "title": "出车记录",
        "headers": ["日期", "姓名", "车牌号", "出发地", "目的地", "提交时间"],
        "kinds": ["text"] * 6,
    },
    "refuel": {
        "title": "加油记录",
        "headers": ["日期", "姓名", "车牌号", "里程(km)", "行驶(km)", "油价(元/L)",
                    "加油量(L)", "金额(元)", "油耗(L/100km)", "提交时间"],
        "kinds": ["text", "text", "text", "number", "number", "number",
                  "number", "number", "number", "text"],
    },
    "maintenance": {
        "title": "保养记录",
        "headers": ["时间", "姓名", "车牌号", "保养项目", "费用(元)", "备注", "提交时间"],
        "kinds": ["text", "text", "text", "text", "number", "text", "text"],
    },
}


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, file=sys.stderr)


# ---------- wecom-cli 调用 ----------
def run_cli(args):
    """执行 wecom-cli 子命令，返回 (ok, data)。args 如 ["sheet", "get", "--json", "{...}"]"""
    try:
        proc = subprocess.run(
            [WECOM_CLI] + args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except FileNotFoundError:
        return False, {"error": "wecom-cli 未找到: %s" % WECOM_CLI}
    except subprocess.TimeoutExpired:
        return False, {"error": "wecom-cli 调用超时"}
    out = (proc.stdout or "").strip()
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError:
        data = {"raw": out}
    if proc.returncode != 0 or data.get("errcode") not in (None, 0):
        return False, data
    return True, data


# ---------- 配置 ----------
def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"docid": "", "url": "", "sheet_ids": {}, "enabled": True}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------- 建表 ----------
def _cell(v, kind="text"):
    if kind == "number":
        try:
            n = float(v)
        except (TypeError, ValueError):
            n = 0.0
        return {"cell_value": {"number": n}, "data_type": "NUMBER", "cell_format": {}}
    return {"cell_value": {"text": "" if v is None else str(v)},
            "data_type": "TEXT", "cell_format": {}}


def _header_row(headers):
    return {"values": [_cell(h, "text") for h in headers]}


def setup_sync_sheet(force=False):
    """幂等创建同步表。返回 (ok, docid, url, sheet_ids)。

    注意：wecom-cli 当前机器人无「搜索与获取文档内容」权限（851008），
    sheet get / ranges get 均不可用，故子表 sheet_id 只能通过
    subsheets add 的返回值捕获；默认空子表无法获取 id，保留在表内，
    用户可在企业微信中手动删除。
    """
    cfg = load_config()
    if not force and cfg.get("docid") and cfg.get("sheet_ids"):
        return True, cfg["docid"], cfg.get("url", ""), cfg.get("sheet_ids", {})

    # 1. 创建空表
    ok, data = run_cli(["sheet", "create", "--json", json.dumps(
        {"doc_name": DOC_NAME}, ensure_ascii=False)])
    if not ok:
        log("建表失败: %s" % json.dumps(data, ensure_ascii=False)[:300])
        return False, "", "", {}
    docid = data.get("docid", "")
    url = data.get("url", "")
    log("已创建同步表: %s" % url)

    # 2. 依次添加三个子表，捕获 sheet_id
    sheet_ids = {}
    for key in ("trip", "refuel", "maintenance"):
        title = SHEET_DEFS[key]["title"]
        ok, data = run_cli(["sheet", "subsheets", "add", "--json", json.dumps(
            {"docid": docid, "sheet": {"title": title}}, ensure_ascii=False)])
        sid = data.get("sheet", {}).get("sheet_id", "")
        if ok and sid:
            sheet_ids[title] = sid
            log("已添加子表: %s (%s)" % (title, sid))
        else:
            log("添加子表失败 %s: %s" % (title, json.dumps(data, ensure_ascii=False)[:200]))

    # 3. 写入表头（A1）
    for key in ("trip", "refuel", "maintenance"):
        title = SHEET_DEFS[key]["title"]
        sid = sheet_ids.get(title)
        if not sid:
            continue
        run_cli(["sheet", "contents", "update", "--json", json.dumps({
            "docid": docid, "sheet_id": sid,
            "grid_data": {"start_row": 0, "start_column": 0,
                          "rows": [_header_row(SHEET_DEFS[key]["headers"])]},
        }, ensure_ascii=False)])
    log("子表表头写入完成")

    cfg.update({"docid": docid, "url": url, "sheet_ids": sheet_ids,
                "enabled": True, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    save_config(cfg)
    return True, docid, url, sheet_ids


def ensure_ready():
    """确保同步表已建好；配置缺失时自动创建。返回 (ok, cfg)"""
    cfg = load_config()
    if not cfg.get("docid"):
        ok, docid, url, sheet_ids = setup_sync_sheet()
        if not ok:
            return False, cfg
        cfg = load_config()
    if not cfg.get("enabled", True):
        return False, cfg
    return True, cfg


# ---------- 追加行 ----------
def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_values(kind, rec):
    d = SHEET_DEFS[kind]
    if kind == "trip":
        values = [rec.get("trip_date", ""), rec.get("name", ""), rec.get("plate", ""),
                  rec.get("origin", ""), rec.get("destination", ""), _now_str()]
    elif kind == "refuel":
        values = [rec.get("refuel_date", ""), rec.get("name", ""), rec.get("plate", ""),
                  rec.get("odometer", 0), rec.get("travel_km", 0), rec.get("oil_price", 0),
                  rec.get("liters", 0), rec.get("amount", 0), rec.get("fuel_consumption", 0),
                  _now_str()]
    else:  # maintenance
        values = [rec.get("maintain_time", ""), rec.get("name", ""), rec.get("plate", ""),
                  rec.get("items", ""), rec.get("cost", 0), rec.get("remark", ""), _now_str()]
    return [_cell(v, k) for v, k in zip(values, d["kinds"])]


def _record_status(kind, rec_id, ok, msg):
    """记录最近一次同步结果到 sync_status.json（供 /api/sync/status 展示）"""
    try:
        items = json.load(open(STATUS_PATH, encoding="utf-8")) if os.path.exists(STATUS_PATH) else []
    except (OSError, json.JSONDecodeError):
        items = []
    items.insert(0, {
        "kind": kind, "id": rec_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ok": bool(ok), "msg": str(msg)[:200],
    })
    items = items[:MAX_STATUS]
    try:
        with open(STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def get_status():
    """同步状态：配置 + 最近同步结果。"""
    cfg = load_config()
    try:
        recent = json.load(open(STATUS_PATH, encoding="utf-8")) if os.path.exists(STATUS_PATH) else []
    except (OSError, json.JSONDecodeError):
        recent = []
    ok_count = sum(1 for r in recent if r.get("ok"))
    return {
        "enabled": cfg.get("enabled", True),
        "ready": bool(cfg.get("docid") and cfg.get("sheet_ids")),
        "url": cfg.get("url", ""),
        "sheet_ids": cfg.get("sheet_ids", {}),
        "recent": recent[:20],
        "summary": {"total": len(recent), "ok": ok_count, "fail": len(recent) - ok_count},
    }


def sync_record(kind, rec):
    """追加一行到同步表。kind: trip/refuel/maintenance；rec 为 dict（含 id 用于日志）。
    返回 (ok, msg)。"""
    if kind not in SHEET_DEFS:
        return False, "未知类型: %s" % kind
    ok, cfg = ensure_ready()
    if not ok:
        _record_status(kind, rec.get("id", ""), False, "同步表不可用（未配置或已禁用）")
        return False, "同步表不可用（未配置或已禁用）"
    sheet_id = cfg.get("sheet_ids", {}).get(SHEET_DEFS[kind]["title"], "")
    if not sheet_id:
        _record_status(kind, rec.get("id", ""), False, "子表未找到: %s" % SHEET_DEFS[kind]["title"])
        return False, "子表未找到: %s" % SHEET_DEFS[kind]["title"]
    row = {"values": _row_values(kind, rec)}
    payload = json.dumps({"docid": cfg["docid"], "sheet_id": sheet_id, "row": row},
                         ensure_ascii=False)
    ok, data = run_cli(["sheet", "rows", "append", "--json", payload])
    if ok:
        log("同步成功 %s #%s %s %s" % (kind, rec.get("id", ""), rec.get("name", ""),
                                       rec.get("plate", "")))
        _record_status(kind, rec.get("id", ""), True, "ok")
        return True, "ok"
    msg = json.dumps(data, ensure_ascii=False)[:200]
    log("同步失败 %s #%s: %s" % (kind, rec.get("id", ""), msg))
    _record_status(kind, rec.get("id", ""), False, msg)
    return False, msg


if __name__ == "__main__":
    ok, docid, url, sheet_ids = setup_sync_sheet(force=False)
    print("setup ok:", ok)
    print("docid:", docid)
    print("url:", url)
    print("sheet_ids:", json.dumps(sheet_ids, ensure_ascii=False))
