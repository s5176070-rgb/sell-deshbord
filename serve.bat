@echo off
title Market Stress Server
REM Keeps the dashboard server up. A shortcut in the Startup folder runs this
REM minimized at logon:
REM   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Market Stress Server.lnk
REM
REM The server is the only thing that updates anything: the page is always live
REM at the address below, the two buttons rebuild on demand, and it re-analyses
REM itself once per trading day, an hour after the New York close. There is
REM deliberately no second scheduled job doing the same work - two
REM processes would race for breadth.csv and each spend the day's 25 API calls
REM believing it had all of them.
REM
REM   http://127.0.0.1:8765
REM
REM This window stays open on purpose. Closing it, or ctrl-c, stops the server.

cd /d "%~dp0"
set "PY=C:\Users\97252\thech analisis\.venv\Scripts\python.exe"

:loop
echo. >> daily.log
echo ==== server start %date% %time% >> daily.log
"%PY%" stress.py --serve --no-open >> daily.log 2>&1

REM Exit 3 is the port guard saying something else is already serving - that is
REM an answer, not a failure, so stop instead of fighting it in a loop.
if errorlevel 3 (
  echo ==== already running elsewhere, not restarting >> daily.log
  goto :eof
)

REM Anything else means it fell over. A dashboard that dies quietly at 3am and
REM is still dead at nine is worse than one that restarts itself.
echo ==== exited %date% %time%, restarting in 30s >> daily.log
timeout /t 30 /nobreak >nul
goto loop
