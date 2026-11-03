@echo off
rem 항로 리스크 앱 실행 (윈도우 로그인 시 start_hidden.vbs 가 창 없이 이 파일을 실행)
rem 로그: app.log
cd /d "%~dp0"

rem 이미 5000 포트에서 실행 중이면 다시 띄우지 않음
netstat -ano | findstr /R /C:":5000 .*LISTENING" >nul && exit /b 0

"C:\Users\user\miniforge3\python.exe" app.py >> app.log 2>&1
