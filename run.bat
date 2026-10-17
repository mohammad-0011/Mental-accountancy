@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo در حال اجرای برنامه حسابداری صبا - نسخه باتری فروشان...
python run.py
pause
