# -*- coding: utf-8 -*-
"""
端到端联调测试：模拟小程序完整使用流程
运行前先启动后端：python app.py
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8081"
PASS, FAIL = 0, 0


def call(method, path, body=None, token=None, files=None):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if files:
        import uuid
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in files.items():
            if isinstance(v, bytes):
                parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="p.jpg"\r\n'
                              'Content-Type: image/jpeg\r\n\r\n' % (boundary, k)).encode())
                parts.append(v + b"\r\n")
            else:
                parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                              % (boundary, k, v)).encode())
        parts.append(("--%s--\r\n" % boundary).encode())
        data = b"".join(parts)
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": "http %s" % e.code}


def download(path, token=None):
    """下载二进制文件，返回 (status, bytes)。"""
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = urllib.request.Request(BASE + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ %s%s" % (name, (" - " + extra if extra else "")))
    else:
        FAIL += 1
        print("  ✗ %s%s" % (name, (" - " + extra if extra else "")))


def main():
    print("== 1. 登录 ==")
    s, r = call("POST", "/api/login", {"userid": "e2e001"})
    check("管理员/司机登录", s == 200 and r.get("ok"), str(r)[:80])
    token = r["data"]["token"]

    print("== 1.5 当前用户 /api/me ==")
    s, r = call("GET", "/api/me")
    check("无 token 访问 me 被拒", s == 401)
    s, r = call("GET", "/api/me", token=token)
    check("me 返回用户信息", s == 200 and r.get("data", {}).get("userid") == "e2e001"
          and "name" in r["data"] and "debug_mode" in r["data"], str(r)[:100])

    print("== 2. 基础选项 ==")
    s, r = call("GET", "/api/options", token=token)
    check("获取车辆/地点", s == 200 and "vehicles" in r.get("data", {}))
    has_veh = len(r["data"]["vehicles"]) > 0

    print("== 3. 提交出车 ==")
    plate = "粤B12345" if has_veh else "测试车"
    s, r = call("POST", "/api/trips", {"plate": plate, "origin": "仓库", "destination": "常平"}, token)
    check("提交出车", s == 200 and r.get("ok"))
    s, r = call("POST", "/api/trips", {"plate": "", "origin": "x", "destination": "y"}, token)
    check("空车牌被拒绝", s == 400)

    print("== 4. 提交加油 ==")
    s, r = call("POST", "/api/refuels", {"refuel_date": "2026-08-17", "odometer": 50100,
                                         "travel_km": 100, "oil_price": 7.5, "liters": 13.3,
                                         "amount": 99.75}, token)
    check("提交加油", s == 200 and r.get("ok"))
    s, r = call("POST", "/api/refuels", {"travel_km": 50, "liters": 5}, token)
    fc = r.get("data", {}).get("msg")
    check("油耗自动计算接口可用", s == 200, str(fc))

    print("== 5. 提交保养（照片） ==")
    s, r = call("POST", "/api/maintenances",
                files={"maintain_time": "2026-08-17 09:30", "items": "更换机油",
                       "cost": "300", "photo": b"\xff\xd8\xff\xe0fake"},
                token=token)
    check("保养+照片上传", s == 200 and r["data"].get("photo"), str(r)[:80])

    print("== 6. 报表 ==")
    s, r = call("GET", "/api/reports/trips?from=2026-08-01&to=2026-08-31&group_by=name", token=token)
    check("出车报表", s == 200 and "summary" in r.get("data", {}))
    s, r = call("GET", "/api/reports/refuels?group_by=plate", token=token)
    check("加油报表", s == 200 and "summary" in r["data"] and r["data"]["summary"]["cnt"] >= 1)
    s, r = call("GET", "/api/reports/maintenances?group_by=name", token=token)
    check("保养报表", s == 200 and r["data"]["summary"]["cnt"] >= 1)

    print("== 6.5 分组汇总 ==")
    s, r = call("GET", "/api/summary?from=2026-08-01&to=2026-08-31", token=token)
    check("分组汇总接口", s == 200 and "by_person" in r.get("data", {})
          and "by_vehicle" in r.get("data", {}), str(r)[:80])
    persons = r["data"].get("by_person", [])
    vehicles = r["data"].get("by_vehicle", [])
    check("按人汇总含出车数据", any(p.get("trip_cnt", 0) > 0 for p in persons), str(persons)[:100])
    check("按车辆汇总非空", len(vehicles) > 0, str(vehicles)[:100])

    print("== 7. 导出 Excel ==")
    for kind in ("trips", "refuels", "maintenances"):
        s, content = download("/api/export/%s?from=2026-08-01&to=2026-08-31" % kind, token)
        check("导出 %s" % kind, s == 200 and content[:2] == b"PK",
              "%dB %s" % (len(content), content[:2]))
    s, content = download("/api/export/badkind", token)
    check("非法导出类型被拒", s == 400)
    s, content = download("/api/export/trips")
    check("未登录导出被拒", s == 401)

    print("== 8. 权限 ==")
    s, r = call("GET", "/api/admin/vehicles", token=token)
    check("普通用户访问管理接口被拒", s == 403, str(r)[:60])
    s, r = call("GET", "/api/options")
    check("未登录被拒", s == 401)

    print("== 9. 网页端与在线表格同步 ==")
    s, r = call("POST", "/api/web/login", {"password": "wrong"})
    check("网页登录错误密码被拒", s == 401)
    s, r = call("POST", "/api/web/login", {"password": "jcf2026"})
    check("网页登录正确密码", s == 200 and r.get("ok"), str(r)[:60])
    web_token = r["data"]["token"]
    s, r = call("GET", "/api/reports/trips?from=2026-08-01&to=2026-08-31", token=web_token)
    check("网页 token 访问报表", s == 200 and "summary" in r.get("data", {}))
    s, r = call("GET", "/api/sync/status", token=web_token)
    check("同步状态接口", s == 200 and "ready" in r.get("data", {}),
          "ready=%s" % r.get("data", {}).get("ready"))
    s, r = call("POST", "/api/sync/push", {"kind": "trip", "id": 1}, token=token)
    check("普通用户重推被拒", s == 403)
    s, r = call("POST", "/api/sync/setup", {}, token=token)
    check("普通用户初始化被拒", s == 403)

    print("== 10. 用户管理 ==")
    # 网页端带账号登录；系统无管理员时首个带账号登录者自动成为管理员
    s, r = call("POST", "/api/web/login", {"password": "jcf2026", "userid": "adm001"})
    check("网页登录带账号", s == 200 and "is_admin" in r.get("data", {}), str(r)[:80])
    adm_token = r["data"]["token"]
    if r["data"].get("is_admin"):
        s, r = call("GET", "/api/admin/users", token=adm_token)
        check("管理员获取用户列表", s == 200 and "users" in r.get("data", {}),
              "total=%s" % r.get("data", {}).get("total"))
        s, r = call("POST", "/api/admin/users",
                    {"userid": "user100", "name": "测试员工", "role": "user"}, adm_token)
        check("管理员新增用户", s == 200 and r.get("ok"), str(r)[:60])
        s, r = call("POST", "/api/admin/users", {"userid": "user100", "name": "重复"}, adm_token)
        check("重复新增被拒", s == 400)
        s, r = call("PATCH", "/api/admin/users/user100", {"role": "admin"}, adm_token)
        check("设为管理员", s == 200 and r.get("ok"))
        s, r = call("PATCH", "/api/admin/users/user100", {"status": "disabled"}, adm_token)
        check("禁用用户", s == 200 and r.get("ok"))
        s, r = call("POST", "/api/login", {"userid": "user100"})
        ut = r.get("data", {}).get("token", "") if s == 200 else ""
        if ut:
            s, r = call("POST", "/api/trips", {"plate": "粤T0001", "origin": "A", "destination": "B"}, ut)
            check("禁用用户提交出车被拒", s == 403, str(r)[:60])
        s, r = call("PATCH", "/api/admin/users/adm001", {"role": "user"}, adm_token)
        check("不能取消自己的管理员", s == 400, str(r)[:60])
        s, r = call("PATCH", "/api/admin/users/adm001", {"status": "disabled"}, adm_token)
        check("不能禁用自己", s == 400)
        # 清理：user100 恢复并降级为普通用户，避免污染后续运行
        call("PATCH", "/api/admin/users/user100", {"status": "active", "role": "user"}, adm_token)
    else:
        print("  ⚠ adm001 不是管理员（系统已有其他管理员），跳过管理员断言")
    s, r = call("GET", "/api/admin/users", token=token)
    check("普通用户访问用户管理被拒", s == 403, str(r)[:60])

    print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
