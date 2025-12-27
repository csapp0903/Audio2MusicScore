#!/bin/bash

# 1. 激活虚拟环境 (根据你的实际路径修改)
source ../venv/bin/activate

# 2. 停止旧的服务 (如果存在)
echo "正在停止旧服务..."
pkill -f "celery worker"
pkill -f "uvicorn"

# 3. 启动 Redis (确保它开着)
sudo systemctl start redis-server

# 4. 启动 Celery Worker (后台运行)
# 输出日志到 celery.log
echo "正在启动 Celery Worker..."
nohup celery -A app.tasks worker --loglevel=info > celery.log 2>&1 &

# 5. 启动 FastAPI Server (后台运行)
# 输出日志到 api.log
echo "正在启动 FastAPI..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &

echo "服务已启动！"
echo "查看 API 日志: tail -f api.log"
echo "查看 Worker 日志: tail -f celery.log"
