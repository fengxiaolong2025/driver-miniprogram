# 金成峰司机助手 · 后端容器镜像（腾讯云 CloudBase 云托管部署）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先装依赖（利用镜像层缓存）
COPY server/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# 拷贝后端代码
COPY server/ ./server/

# 数据目录（挂载卷会覆盖此路径，见 CLOUD_DEPLOY.md）
RUN mkdir -p /data/uploads

# 容器默认配置：数据/照片落在 /data（挂载 CFS 持久化）；关闭在线表格同步（wecom-cli 仅本机可用）
ENV DB_PATH=/data/driver.db \
    UPLOAD_DIR=/data/uploads \
    WX_SYNC_ENABLED=0 \
    WX_DEBUG_MODE=0

WORKDIR /app/server
EXPOSE 8081

# 单 worker 多线程：SQLite 文件型数据库在单实例下最安全（务必保持实例数=1）
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:8081", "--timeout", "60", "--graceful-timeout", "30", "app:app"]
