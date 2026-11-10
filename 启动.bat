@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 6G 通感算一体 · 低空医疗配送协同调度仿真平台...
echo 浏览器将自动打开 http://localhost:8501
python -m streamlit run app.py --server.port 8501
pause
