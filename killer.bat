@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
title PT Nacional - Sentinel Launcher
chcp 65001 >nul

set "CLI_MODE=0"
if not "%~1"=="" (
  set "CLI_MODE=1"
  if /I "%~1"=="start" goto start_dev
  if /I "%~1"=="prod" goto start_prod
  if /I "%~1"=="check" goto check_env
  if /I "%~1"=="path" goto show_path
  if /I "%~1"=="kill" goto kill_only
  if /I "%~1"=="exit" goto end_ok
  echo [ERROR] Argumento no valido: %~1
  echo         Usa: killer.bat ^<start^|prod^|check^|path^|kill^|exit^>
  exit /b 2
)

:menu
cls
echo ============================================================
echo   PT NACIONAL ^| COMMAND CENTER BOOT MENU
echo ============================================================
echo.
echo   [1] Iniciar en MODO DESARROLLO (Dev Mode)
echo   [2] Iniciar en MODO PRODUCCION (Enterprise Build - Sin errores UI)
echo   [3] Verificar entorno y dependencias
echo   [4] Mostrar ruta de trabajo
echo   [5] Aniquilar procesos y liberar puertos (Limpieza Forense)
echo   [6] Salir
echo.
set /p "opt=Selecciona una opcion [1-6]: "

if "%opt%"=="1" goto start_dev
if "%opt%"=="2" goto start_prod
if "%opt%"=="3" goto check_env
if "%opt%"=="4" goto show_path
if "%opt%"=="5" goto kill_only
if "%opt%"=="6" goto end_ok

echo.
echo [ERROR] Opcion invalida. Intenta de nuevo.
timeout /t 2 >nul
goto menu

:resolve_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "backend\venv\Scripts\python.exe" (
  set "PYTHON_EXE=backend\venv\Scripts\python.exe"
) else if exist "backend\venv\bin\python" (
  set "PYTHON_EXE=backend\venv\bin\python"
) else (
  set "PYTHON_EXE=python"
)
exit /b 0

:show_path
cls
echo ============================================================
echo   RUTA DE TRABAJO
echo ============================================================
echo.
echo %cd%
echo.
if "%CLI_MODE%"=="1" exit /b 0
set /p "dummy=Presiona Enter para volver al menu..."
goto menu

:kill_only
cls
echo ============================================================
echo   PROTOCOLO DE LIMPIEZA FORENSE (ANIQUILACION DE PUERTOS)
echo ============================================================
echo.
echo [*] Escaneando puerto 8000 (Backend / Uvicorn)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo [!] Proceso detectado en PID: %%a. Ejecutando aniquilacion...
    taskkill /F /PID %%a >nul 2>&1
    echo [+] Puerto 8000 liberado.
)

echo [*] Escaneando puerto 3000 (Frontend / Next.js)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING') do (
    echo [!] Proceso Node detectado en PID: %%a. Ejecutando aniquilacion...
    taskkill /F /PID %%a >nul 2>&1
    echo [+] Puerto 3000 liberado.
)

echo [*] Deteniendo contenedores Docker huerfanos (PostgreSQL / Redis)...
docker-compose down >nul 2>&1

echo.
echo [OK] Limpieza profunda completada. Entorno esterilizado.
echo.
if "%CLI_MODE%"=="1" exit /b 0
set /p "dummy=Presiona Enter para volver al menu..."
goto menu

:check_env
cls
echo ============================================================
echo   VERIFICACION DE ENTORNO
echo ============================================================
echo.
call :resolve_python
echo [*] Usando Python: %PYTHON_EXE%
%PYTHON_EXE% --version
echo.
echo [*] Verificando Node.js...
node --version
echo.
echo [*] Verificando Docker...
docker --version
echo.
if "%CLI_MODE%"=="1" exit /b 0
set /p "dummy=Presiona Enter para volver al menu..."
goto menu

:start_dev
cls
echo ============================================================
echo   ARRANQUE EN MODO DESARROLLO (DEV MODE)
echo ============================================================
echo.
set "ENV_MODE=dev"
goto run_sentinel

:start_prod
cls
echo ============================================================
echo   ARRANQUE EN MODO PRODUCCION (ENTERPRISE BUILD)
echo ============================================================
echo [!] NOTA: El Sentinel compilara el frontend antes de iniciar.
echo [!] Esto eliminara los overlays de error y optimizara la velocidad.
echo.
set "ENV_MODE=prod"
goto run_sentinel

:run_sentinel
if not exist "boot_sentinel.py" (
  echo [FATAL] Falta boot_sentinel.py en la raiz del proyecto.
  if "%CLI_MODE%"=="1" exit /b 1
  set /p "dummy=Presiona Enter para volver al menu..."
  goto menu
)

call :resolve_python
if errorlevel 1 (
  echo.
  if "%CLI_MODE%"=="1" exit /b 1
  set /p "dummy=Presiona Enter para volver al menu..."
  goto menu
)

echo [INFO] Ejecutando boot_sentinel.py con: %PYTHON_EXE% (Modo: %ENV_MODE%)
echo [INFO] Para apagar todo de forma limpia usa Ctrl+C.
echo.

:: Pasamos la variable de entorno al Sentinel
set "COMMAND_CENTER_ENV=%ENV_MODE%"
call "%PYTHON_EXE%" boot_sentinel.py
set "BOOT_EXIT=%errorlevel%"

echo.
if not "%BOOT_EXIT%"=="0" (
  echo [AVISO] El sistema se detuvo. Si fue un error, revisa los logs.
)
if "%CLI_MODE%"=="1" exit /b %BOOT_EXIT%
set /p "dummy=Presiona Enter para volver al menu..."
goto menu

:end_ok
exit /b 0
