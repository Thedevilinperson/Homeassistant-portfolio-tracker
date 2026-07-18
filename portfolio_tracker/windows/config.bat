@echo off
rem ============================================================================
rem  config.bat - Instellingen voor de Windows-versie van Portfolio Tracker
rem ----------------------------------------------------------------------------
rem  Pas dit bestand NIET aan als je het via git bijhoudt. Maak in plaats daarvan
rem  een bestand config.local.bat in deze map met alleen de regels die je wil
rem  wijzigen; dat wordt hieronder automatisch ingelezen en overschrijft de
rem  standaarden. Zo blijft een git pull conflictvrij.
rem ============================================================================

rem --- Waar staat de data (database, FSMA-cache)? -----------------------------
rem  Standaard buiten de repo, zodat een git pull of clone je database nooit
rem  kan raken en de database niet per ongeluk in een commit belandt.
set "DATA_DIR=%LOCALAPPDATA%\PortfolioTracker\data"

rem --- Netwerkadres en poort --------------------------------------------------
rem  127.0.0.1 = alleen bereikbaar op deze PC. Zet op 0.0.0.0 als je de app ook
rem  vanaf je telefoon of een andere PC in je netwerk wil openen (Windows vraagt
rem  dan eenmalig om een firewall-uitzondering).
set "BIND_ADDRESS=127.0.0.1"
set "APP_PORT=8501"

rem --- Tijdzone ---------------------------------------------------------------
set "TZ=Europe/Brussels"

rem --- Browser automatisch openen bij het starten? ----------------------------
set "OPEN_BROWSER=1"

rem --- Achtergrondjobs (koersen ophalen, dagelijks AI-advies) meestarten? -----
rem  Zet op 0 als je de app enkel af en toe opent en geen achtergrondproces wil.
set "RUN_SCHEDULER=1"

rem ============================================================================
rem  Lokale overrides - niets hieronder aanpassen
rem ============================================================================
if exist "%~dp0config.local.bat" call "%~dp0config.local.bat"

rem Afgeleide paden
set "WIN_DIR=%~dp0"
set "APP_DIR=%~dp0.."
set "VENV_DIR=%APP_DIR%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "LOG_DIR=%WIN_DIR%logs"
set "PID_FILE=%WIN_DIR%scheduler.pid"
