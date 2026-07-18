@echo off
setlocal
rem ============================================================================
rem  stop.bat - De achtergrondscheduler stoppen
rem  Wordt ook automatisch aangeroepen door start.bat (voor en na het draaien).
rem  Met de optie --quiet blijft de uitvoer beperkt.
rem ============================================================================
call "%~dp0config.bat"

set "QUIET=0"
if /I "%~1"=="--quiet" set "QUIET=1"

if not exist "%PID_FILE%" (
    if "%QUIET%"=="0" echo Geen draaiende scheduler gevonden.
    goto :einde
)

set /p SCHED_PID=<"%PID_FILE%"
if not defined SCHED_PID (
    del "%PID_FILE%" >nul 2>&1
    goto :einde
)

rem Bestaat dat proces nog? Een PID-bestand kan achterblijven na een harde afsluiting,
rem en een hergebruikt PID zomaar afschieten zou een ander programma kunnen raken.
tasklist /FI "PID eq %SCHED_PID%" /FI "IMAGENAME eq python.exe" 2>nul | find "%SCHED_PID%" >nul
if %ERRORLEVEL% NEQ 0 (
    if "%QUIET%"=="0" echo Scheduler draaide niet meer; verouderd PID-bestand opgeruimd.
    del "%PID_FILE%" >nul 2>&1
    goto :einde
)

taskkill /PID %SCHED_PID% /T /F >nul 2>&1
if %ERRORLEVEL%==0 (
    if "%QUIET%"=="0" echo Scheduler gestopt, PID %SCHED_PID%.
) else (
    echo [WAARSCHUWING] Kon proces %SCHED_PID% niet stoppen.
)
del "%PID_FILE%" >nul 2>&1

:einde
if "%QUIET%"=="0" if "%~1"=="" pause
endlocal
exit /b 0
