@echo off
chcp 65001 >nul
cd /d %~dp0

set PY="C:\Users\75720\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist %PY% set PY=python

echo ==========================================
echo   金成峰司机助手 · 后端 API 启动
echo   健康检查: http://127.0.0.1:8081/health
echo ==========================================
%PY% app.py
pause
