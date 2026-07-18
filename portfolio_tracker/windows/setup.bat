@echo off
setlocal enabledelayedexpansion
rem ============================================================================
rem  setup.bat - Eenmalige installatie van Portfolio Tracker op Windows
rem  Maakt een virtuele omgeving, installeert de pakketten en initialiseert de
rem  database. Opnieuw uitvoeren is veilig: bestaande data blijft ongemoeid.
rem ============================================================================
call "%~dp0config.bat"

echo ============================================
echo  Portfolio Tracker - installatie
echo ============================================
echo.

rem --- 1. Python zoeken -------------------------------------------------------
set "LAUNCHER="
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 set "LAUNCHER=py -3"
if not defined LAUNCHER where python >nul 2>&1
if not defined LAUNCHER if %ERRORLEVEL% EQU 0 set "LAUNCHER=python"

if defined LAUNCHER goto :python_gevonden
echo [FOUT] Python is niet gevonden.
echo        Installeer Python 3.11 of 3.12 van https://www.python.org/downloads/
echo        en vink tijdens de installatie "Add python.exe to PATH" aan.
goto :fail
:python_gevonden

rem --- 2. Versie controleren --------------------------------------------------
rem  De versie wordt uit "python -V" gelezen en niet uit een python -c fragment:
rem  aanhalingstekens binnen een for /f-commando botsen met de batch-parser.
set "PYVER="
for /f "usebackq tokens=2" %%a in (`%LAUNCHER% -V 2^>^&1`) do set "PYVER=%%a"
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set "PYMAJOR=%%a"
    set "PYMINOR=%%b"
)

echo Gevonden Python: %PYVER%

if "%PYMAJOR%"=="3" goto :major_ok
echo [FOUT] Python 3 is vereist, gevonden versie %PYVER%.
goto :fail
:major_ok

if %PYMINOR% GEQ 10 goto :minor_ok
echo [FOUT] Python 3.10 of hoger is vereist, gevonden %PYVER%.
goto :fail
:minor_ok

if %PYMINOR% LSS 13 goto :versie_ok
echo [FOUT] Python %PYVER% wordt nog niet ondersteund.
echo        De app draait op numpy 1.x en daarvan bestaan geen kant-en-klare
echo        pakketten voor 3.13 of hoger. De installatie zou proberen te
echo        compileren en dat mislukt zonder Visual Studio Build Tools.
echo        Installeer Python 3.11 of 3.12 naast je huidige versie.
goto :fail
:versie_ok

rem --- 3. Virtuele omgeving ---------------------------------------------------
if not exist "%PYTHON%" goto :venv_maken
echo Virtuele omgeving bestaat al: %VENV_DIR%
goto :venv_klaar
:venv_maken
echo Virtuele omgeving aanmaken in %VENV_DIR% ...
%LAUNCHER% -m venv "%VENV_DIR%"
if !ERRORLEVEL! NEQ 0 goto :fail
:venv_klaar

rem --- 4. Pakketten -----------------------------------------------------------
echo.
echo Pakketten installeren. De eerste keer duurt dit enkele minuten ...
"%PYTHON%" -m pip install --upgrade pip --quiet
if !ERRORLEVEL! NEQ 0 goto :fail
"%PYTHON%" -m pip install -r "%WIN_DIR%requirements-windows.txt"
if !ERRORLEVEL! NEQ 0 goto :fail

rem --- 5. Streamlit-thema -----------------------------------------------------
rem  Streamlit leest zijn instellingen uit .streamlit\config.toml in de werkmap.
rem  In de repo staat config.toml in de hoofdmap; die wordt hier op de plek gezet
rem  waar Streamlit hem effectief vindt, zodat het donkere thema ook lokaal werkt.
if not exist "%APP_DIR%\.streamlit" mkdir "%APP_DIR%\.streamlit"
if exist "%APP_DIR%\.streamlit\config.toml" goto :thema_klaar
if not exist "%APP_DIR%\config.toml" goto :thema_klaar
copy /Y "%APP_DIR%\config.toml" "%APP_DIR%\.streamlit\config.toml" >nul
echo Streamlit-thema overgenomen uit config.toml
:thema_klaar

rem --- 6. Datamap en database -------------------------------------------------
echo.
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
echo Datamap: %DATA_DIR%

echo Database initialiseren ...
pushd "%APP_DIR%"
"%PYTHON%" -c "import database; database.init_db(); print('   Database klaar:', database.DB_PATH)"
set "RC=!ERRORLEVEL!"
popd
if !RC! NEQ 0 goto :fail

echo.
echo ============================================
echo  Installatie voltooid.
echo.
echo  Start de app met:  start.bat
echo.
echo  Heb je al een database van de Home Assistant add-on? Kopieer dan
echo  portfolio.db uit \share\portfolio_tracker naar de datamap hierboven,
echo  voordat je de app voor het eerst start.
echo ============================================
pause
exit /b 0

:fail
echo.
echo [AFGEBROKEN] De installatie is niet voltooid. Zie de melding hierboven.
pause
exit /b 1
