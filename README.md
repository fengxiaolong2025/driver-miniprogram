# 金成峰司机助手 · 企业微信小程序

司机出车/加油/保养管理小程序，在企业微信中使用。
管理员维护车辆与地点，司机一键提交记录，后台生成三类统计报表。

---

## 系统架构

```
企业微信小程序（miniprogram/）        电脑浏览器（/web 网页端报表）
        │ wx.qy.login / wx.request            │ 密码登录 /api/web/login
        ▼                                     ▼
后端 Flask API（server/app.py，默认 8081 端口）
        │
        ├── SQLite（driver.db） 车辆/地点/出车/加油/保养
        ├── uploads/            保养照片
        └── sync_sheet.py ──异步──▶ 企业微信在线表格「金成峰司机数据同步」
                                 （出车记录/加油记录/保养记录 三子表）
```

> 与现有「群消息统计」系统（webhook 8080 端口）互不影响，可同时运行。

---

## 目录结构

```
driver_miniprogram/
├── miniprogram/            # 小程序前端（微信开发者工具打开）
│   ├── app.js              # 入口：登录（wx.qy.login / 调试登录）
│   ├── utils/api.js        # 请求封装（BASE_URL 在此配置）
│   └── pages/
│       ├── index/          # 首页（功能入口 + 管理员入口）
│       ├── trip/           # 我要出车
│       ├── refuel/         # 我要加油
│       ├── maintain/       # 我要保养（拍照上传）
│       ├── reports/        # 报表统计（出车/加油/保养）
│       └── admin/          # 管理设置（仅管理员可见）
├── server/                 # 后端 API
│   ├── app.py              # Flask 服务（全部接口）
│   ├── auth.py             # 企业微信登录/鉴权
│   ├── db.py               # SQLite 数据层
│   ├── excel_export.py     # 报表导出 Excel（openpyxl）
│   ├── sync_sheet.py       # 在线表格自动同步（wecom-cli）
│   ├── sync_config.json    # 同步表配置（docid/子表 id，首次自动生成）
│   ├── web/index.html      # 网页端报表页面（/web）
│   ├── config.json         # 配置（corpid/secret/管理员/端口/web_password）
│   ├── e2e_test.py         # 端到端联调测试
│   └── start_server.bat    # Windows 一键启动
└── project.config.json     # 微信开发者工具项目配置
```

---

## 快速开始（本地联调）

### 1. 启动后端

```bash
cd D:\1001\金成峰\driver_miniprogram\server
python app.py
# 或直接双击 start_server.bat
```

看到 `API 启动: http://127.0.0.1:8081/health` 即成功。

默认 **debug_mode=true**：登录不依赖企业微信后台，直接以 userid（默认 dev001）登录，
首页底部有「切换调试用户」入口，可切换到任意 userid 测试管理员功能。

### 2. 导入小程序

1. 打开**微信开发者工具**（下载：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html）
2. 导入项目，选择目录 `D:\1001\金成峰\driver_miniprogram`
3. AppID：先用「测试号」，或用企业微信小程序 AppID
4. **详情 → 本地设置 → 勾选「不校验合法域名」**（本地 http 调试必需）
5. 编译运行，模拟器内即出现「金成峰司机助手」首页

> 真机预览：把 `miniprogram/utils/api.js` 中的 `BASE_URL` 改为电脑局域网 IP
> （如 `http://192.168.1.100:8081`），手机与企业微信需与电脑同一网络。

---

## 企业微信正式配置（发布前必读）

### 1. 创建企业微信小程序

1. 打开**企业微信管理后台**：https://work.weixin.qq.com/wework_admin/
2. **应用管理 → 自建 → 创建应用 → 小程序**（或「创建自建应用」后关联小程序）
3. 记录 **AppID** 与 **Secret**（小程序详情页）

### 2. 填写后端配置 `server/config.json`

```json
{
  "corpid": "企业ID（我的企业 → 企业信息）",
  "secret": "小程序 Secret",
  "admin_userids": ["张三的userid", "李四的userid"],
  "debug_mode": false,
  "listen_port": 8081,
  "web_password": "改成强密码"
}
```

> 管理员 userid 获取：企业微信管理后台 → 通讯录 → 成员详情，URL 末尾或资料中即为 userid。
> 可在调试模式登录后用首页「切换调试用户」逐一确认。

### 3. 上线域名要求（关键）

小程序正式版要求 **HTTPS + ICP 备案域名**：

| 环境 | 域名要求 |
|------|----------|
| 本地调试 | 无（勾选「不校验合法域名」） |
| 体验版/预览 | 后端为 HTTPS 域名或开启调试模式 |
| **正式发布** | **必须 HTTPS 备案域名**，且 `request`/`uploadFile` 合法域名需在小程序后台配置 |

推荐部署方式（二选一）：
- **云服务器直连**：把 `server/` 部署到公网服务器（Python 3 + Flask），配 Nginx + SSL 证书 + 备案域名
- **现有 FRP 服务器**：复用 `121.41.71.134`，但需为 7001 端口配 HTTPS 域名（反向代理 + 证书），或改用 Nginx 直接暴露

### 4. 常见问题

- **登录失败「无法获取 access_token」**：检查 config.json 的 corpid/secret，需为小程序而非普通应用的 Secret
- **wx.qy 未定义**：企业微信专属小程序在企业微信客户端内运行才有 wx.qy；开发者工具/普通微信中走调试登录
- **照片不显示**：报表中照片通过后端域名加载，需保证 downloadFile 合法域名配置

---

## 数据存储

- SQLite 文件：`server/driver.db`（备份该文件即备份全部数据）
- 清空重建：删除 `driver.db` 后重启后端自动建表
- 保养照片：`server/uploads/`

---

## 在线表格自动同步

小程序每提交一条出车/加油/保养记录，后端会自动把该记录**异步追加**到企业微信在线表格
「金成峰司机数据同步」（机器人自建，含 **出车记录 / 加油记录 / 保养记录** 三个子表），
不阻塞接口响应；同步结果记录在 `server/sync_status.json`，可在网页端/小程序侧查看。

- **同步表链接**（首次初始化自动生成，见 `server/sync_config.json` 的 `url`）：
  https://doc.weixin.qq.com/sheet/e3_AIIAgXieAGACNj2VpWmbNSTadUYzy_a
- **为什么不是现有「金成峰司机出车统计」表**：wecom-cli 的机器人身份只能写入
  **机器人自己创建**的文档（企微权限约束），对真人创建的表格无写权限（错误 851008）。
  如需同步到其它表：由同一机器人创建目标表，然后把 `sync_config.json` 的 `docid`、
  `sheet_ids` 改成目标表（子表 id 通过 `subsheets add` 返回值获取）。
- **清空重建同步表**：删掉在线表格后，管理员调用
  `POST /api/sync/setup {"force": true}` 自动重建（旧的空表需在企微中手动删除）。
- **手动重推**：某条记录同步失败时（如机器人临时不可用），管理员调用
  `POST /api/sync/push {"kind":"trip","id":1}` 重推。
- 前置条件：本机已安装 `@wecom/cli`（≥1.1.0）并完成企业微信扫码授权
  （`wecom-cli auth show --status` 输出 `authorized`）。

---

## 网页端报表（电脑浏览器）

后端自带一个报表网页，电脑浏览器打开即可查看与下载，无需安装小程序：

- 访问：`http://<服务器IP>:8081/web`（本机调试：http://127.0.0.1:8081/web）
- 登录密码：`server/config.json` 的 **web_password**（默认 `jcf2026`，正式部署务必修改）
- 功能：出车/加油/保养三类报表切换、日期范围筛选、汇总卡片、明细表格、
  **导出 Excel**（与小程序报表页同源数据），顶部显示在线表格同步状态与同步表链接

---

## 测试

```bash
# 1. 先启动后端
python server/app.py
# 2. 运行端到端测试（23 项断言，含导出/网页端/同步）
python server/e2e_test.py
```

---

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/login | 登录（code 或调试 userid） |
| GET | /api/options | 车辆/出发地/目的地 |
| POST | /api/trips | 提交出车 |
| POST | /api/refuels | 提交加油（油耗自动计算） |
| POST | /api/maintenances | 提交保养（multipart 照片） |
| GET | /api/reports/trips | 出车报表（from/to/group_by） |
| GET | /api/reports/refuels | 加油报表 |
| GET | /api/reports/maintenances | 保养报表 |
| GET | /api/export/trips | 导出出车 Excel（from/to 过滤，返回 .xlsx） |
| GET | /api/export/refuels | 导出加油 Excel |
| GET | /api/export/maintenances | 导出保养 Excel |
| GET/POST/DELETE | /api/admin/vehicles | 管理员：车辆维护 |
| GET/POST/DELETE | /api/admin/locations | 管理员：地点维护（kind=origin/destination） |
| GET | /api/sync/status | 在线表格同步状态（含最近结果） |
| POST | /api/sync/push | 管理员：手动重推记录到在线表格（{kind,id}） |
| POST | /api/sync/setup | 管理员：初始化/重建同步表（{force}） |
| GET | /web | 网页端报表页面 |
| POST | /api/web/login | 网页登录（{password} → token） |
| GET | /health | 健康检查 |
