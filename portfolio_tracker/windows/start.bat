@echo off
setlocal enabledelayedexpansion
rem ============================================================================
rem  start.bat - Portfolio Tracker starten op Windows
rem  Start de scheduler op de achtergrond en Streamlit op de voorgrond.
rem  Sluit je dit venster of druk je Ctrl+C, dan stopt de scheduler mee.
rem ----------------------------------------------------------------------------
rem  Let op bij het aanpassen: dit script vermijdt bewust haakjesblokken
rem  ( if ... ( ) ) rond regels die zelf haakjes bevatten. De batch-parser leest
rem  het eerste sluithaakje in zo'n blok als het einde van het blok, ook binnen
rem  aanhalingstekens. Daarom wordt hier met labels en goto gewerkt.
rem ============================================================================
call "%~dp0config.bat"

echo ============================================
echo  Portfolio Tracker - opstarten
echo  %DATE% %TIME:~0,8%  ^| TZ=%TZ%
echo ============================================

if exist "%PYTHON%" goto :venv_ok
echo [FOUT] Geen virtuele omgeving gevonden.
echo        Voer eerst setup.bat uit.
pause
exit /b 1
:venv_ok

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo Datamap: %DATA_DIR%

rem --- Database bijwerken; de migraties zijn idempotent -----------------------
pushd "%APP_DIR%"
"%PYTHON%" -c "import database; database.init_db()"
if !ERRORLEVEL! EQU 0 goto :db_ok
echo [FOUT] De database kon niet geopend of bijgewerkt worden.
popd
pause
exit /b 1
:db_ok

rem --- Scheduler op de achtergrond -------------------------------------------
rem  Via PowerShell gestart omdat we het proces-ID nodig hebben om het later
rem  gericht te kunnen stoppen. Batch alleen geeft dat niet terug.
if not "%RUN_SCHEDULER%"=="1" goto :geen_scheduler
call "%WIN_DIR%stop.bat" --quiet
set "PS_CMD=(Start-Process -FilePath '%PYTHON%' -ArgumentList 'scheduler.py' -WorkingDirectory '%APP_DIR%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%LOG_DIR%\scheduler.log' -RedirectStandardError '%LOG_DIR%\scheduler.err.log').Id"
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "!PS_CMD!"`) do set "SCHED_PID=%%i"
if not defined SCHED_PID goto :scheduler_mislukt
echo !SCHED_PID!>"%PID_FILE%"
echo Scheduler gestart, PID !SCHED_PID! - log: %LOG_DIR%\scheduler.log
goto :na_scheduler

:scheduler_mislukt
echo [WAARSCHUWING] De scheduler kon niet gestart worden. De app werkt wel, maar
echo                koersen worden dan niet automatisch ververst op de achtergrond.
goto :na_scheduler

:geen_scheduler
echo Scheduler overgeslagen, RUN_SCHEDULER=0

:na_scheduler

rem --- Browser openen ---------------------------------------------------------
if not "%OPEN_BROWSER%"=="1" goto :geen_browser
set "OPEN_HOST=%BIND_ADDRESS%"
if "%BIND_ADDRESS%"=="0.0.0.0" set "OPEN_HOST=localhost"
start "" "http://%OPEN_HOST%:%APP_PORT%"
:geen_browser

rem --- Streamlit op de voorgrond ---------------------------------------------
echo.
echo Streamlit draait op http://%BIND_ADDRESS%:%APP_PORT%
echo Stoppen: druk Ctrl+C of sluit dit venster.
echo.
"%PYTHON%" -m streamlit run app.py --server.port=%APP_PORT% --server.address=%BIND_ADDRESS% --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false

rem --- Opruimen ---------------------------------------------------------------
popd
echo.
echo Streamlit is gestopt. Scheduler afsluiten ...
call "%WIN_DIR%stop.bat" --quiet
echo Klaar.
endlocal
exit /b 0
