@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
title PT Nacional - Sentinel Launcher
chcp 65001 >nul

set "CLI_MODE=0"
if not "%~1"=="" (
  set "CLI_MODE=1"
  if /I "%~1"=="start" goto start_all
  if /I "%~1"=="check" goto check_env
  if /I "%~1"=="path" goto show_path
  if /I "%~1"=="exit" goto end_ok
  echo [ERROR] Argumento no valido: %~1
  echo         Usa: killer.bat ^<start^|check^|path^|exit^>
  exit /b 2
)

:menu
cls
echo ============================================================
echo   PT NACIONAL ^| SENTINEL BOOT MENU
echo ============================================================
echo.
echo   [1] Iniciar sistema completo (Docker + Backend + Frontend)
echo   [2] Verificar entorno y dependencias
echo   [3] Mostrar ruta actual
echo   [4] Salir
echo.
set /p "opt=Selecciona una opcion [1-4]: "

if "%opt%"=="1" goto start_all
if "%opt%"=="2" goto check_env
if "%opt%"=="3" goto show_path
if "%opt%"=="4" goto end_ok

echo.
echo [ERROR] Opcion invalida. Intenta de nuevo.
timeout /t 2 >nul
goto menu

:resolve_python
set "PYTHON_EXE="
set "PYTHON_ARGS="

if exist "backend\venv\Scripts\python.exe" (
  set "PYTHON_EXE=%cd%\backend\venv\Scripts\python.exe"
  goto resolve_done
)

where python >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_EXE=python"
  goto resolve_done
)

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
  goto resolve_done
)

echo.
echo [FATAL] No se encontro Python en el sistema.
echo         Instala Python o crea el entorno backend\venv.
exit /b 1

:resolve_done
exit /b 0

:check_env
cls
echo ============================================================
echo   VERIFICACION DE ENTORNO
echo ============================================================
echo.

if not exist "boot_sentinel.py" (
  echo [FATAL] Falta boot_sentinel.py en la raiz del proyecto.
  echo         Ruta esperada: %cd%\boot_sentinel.py
  echo.
  if "%CLI_MODE%"=="1" exit /b 1
  set /p "dummy=Presiona Enter para volver al menu..."
  goto menu
)
echo [OK] Archivo boot_sentinel.py encontrado.

call :resolve_python
if errorlevel 1 (
  echo.
  if "%CLI_MODE%"=="1" exit /b 1
  set /p "dummy=Presiona Enter para volver al menu..."
  goto menu
)

if defined PYTHON_ARGS (
  echo [OK] Python detectado: %PYTHON_EXE% %PYTHON_ARGS%
) else (
  echo [OK] Python detectado: %PYTHON_EXE%
)

if exist "backend\venv\Scripts\python.exe" (
  echo [OK] Entorno virtual detectado en backend\venv.
) else (
  echo [WARN] No se detecto backend\venv\Scripts\python.exe.
  echo       Se usara Python global como fallback.
)

echo.
echo [INFO] Verificando import de psutil...
if defined PYTHON_ARGS (
  call "%PYTHON_EXE%" %PYTHON_ARGS% -c "import psutil; print('psutil:', psutil.__version__)" 1>nul 2>nul
) else (
  call "%PYTHON_EXE%" -c "import psutil; print('psutil:', psutil.__version__)" 1>nul 2>nul
)
if %errorlevel%==0 (
  echo [OK] psutil disponible.
) else (
  echo [WARN] psutil no disponible en este interprete.
  echo       Ejecuta: pip install psutil
)

echo.
if "%CLI_MODE%"=="1" exit /b 0
set /p "dummy=Presiona Enter para volver al menu..."
goto menu

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

:start_all
cls
echo ============================================================
echo   ARRANQUE COMPLETO DEL SISTEMA
echo ============================================================
echo.

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

if defined PYTHON_ARGS (
  echo [INFO] Ejecutando boot_sentinel.py con: %PYTHON_EXE% %PYTHON_ARGS%
) else (
  echo [INFO] Ejecutando boot_sentinel.py con: %PYTHON_EXE%
)
echo [INFO] Para apagar todo de forma limpia usa Ctrl+C.
echo.

if defined PYTHON_ARGS (
  call "%PYTHON_EXE%" %PYTHON_ARGS% boot_sentinel.py
) else (
  call "%PYTHON_EXE%" boot_sentinel.py
)
set "BOOT_EXIT=%errorlevel%"

echo.
if not "%BOOT_EXIT%"=="0" (
  echo [WARN] boot_sentinel.py termino con codigo %BOOT_EXIT%.
) else (
  echo [OK] boot_sentinel.py finalizo sin errores.
)
echo.
if "%CLI_MODE%"=="1" exit /b %BOOT_EXIT%
set /p "dummy=Presiona Enter para volver al menu..."
goto menu

:end_ok
echo Saliendo...
endlocal
exit /b 0
