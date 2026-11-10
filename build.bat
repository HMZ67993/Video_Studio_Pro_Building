@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title HMZ Video Studio Pro - Local Windows Build

set "APP_NAME=HMZVideoStudioPro"
set "ENTRY=video_studio.py"
set "PYTHON_VERSION=3.12"
set "VENV=%CD%\.hmz_build_venv"
set "PY=%VENV%\Scripts\python.exe"
set "BUILD_DIR=%CD%\build"
set "DIST_DIR=%CD%\dist"
set "AI_DIR=%CD%\.hmz_ai_runtime_stage"
set "TEST_APPDATA=%BUILD_DIR%\selftest-appdata"
set "UNIT_TEST_APPDATA=%BUILD_DIR%\unit-test-appdata"
set "SELFTEST_FILE=%BUILD_DIR%\selftest-ai.txt"

echo ============================================================
echo  HMZ Video Studio Pro - LOCAL BUILD
echo  Python 3.12 x64 / Nuitka / Separate AI runtime
echo ============================================================
echo.

rem ------------------------------------------------------------
rem 1) Require the same Python ABI used by the published AI wheels.
rem    Do not silently build with Python 3.13/3.14 or 32-bit Python.
echo [1/9] Checking Python 3.12 x64 ...
where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python Launcher "py" was not found.
    echo Install Python 3.12 x64 from python.org and enable the Python Launcher.
    goto :failed
)
py -3.12 -c "import sys,struct; print('Python:',sys.version); print('Architecture:',struct.calcsize('P')*8,'bit'); raise SystemExit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.12 x64 is required. This build intentionally rejects other versions.
    goto :failed
)

if not exist "%ENTRY%" (
    echo [ERROR] Entry point not found: %ENTRY%
    goto :failed
)
if not exist "icon.ico" (
    echo [ERROR] icon.ico was not found beside build.bat.
    goto :failed
)

rem ------------------------------------------------------------
rem 2) Always use a clean isolated virtual environment. This avoids
rem    mixing globally installed packages or another Python version.
echo.
echo [2/9] Preparing isolated build environment ...
if exist "%VENV%" rmdir /s /q "%VENV%"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
py -3.12 -m venv "%VENV%"
if errorlevel 1 goto :failed
if not exist "%PY%" (
    echo [ERROR] Virtual environment Python was not created.
    goto :failed
)
"%PY%" -m pip install --disable-pip-version-check --upgrade "pip==26.3"
if errorlevel 1 goto :failed

rem ------------------------------------------------------------
rem 3) Pin the build stack to the versions used by the successful
rem    Windows/Python 3.12 build. This prevents surprise major upgrades.
echo.
echo [3/9] Installing pinned application/build dependencies ...
(
 echo PyQt6==6.12.0
 echo cryptography==50.0.2
 echo opencv-python-headless==5.0.0.93
 echo numpy==2.5.4
 echo Pillow==13.0.0
 echo arabic-reshaper==3.1.0
 echo python-bidi==0.6.12
 echo nuitka==4.3.5
 echo ordered-set==4.1.0
 echo zstandard==0.25.0
 echo pytest==9.2.0
) > "%BUILD_DIR%\local-build-constraints.txt"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt -c "%BUILD_DIR%\local-build-constraints.txt"
if errorlevel 1 (
    echo [ERROR] Installing the pinned application/build dependencies failed.
    goto :failed
)
"%PY%" -m pip check
if errorlevel 1 (
    echo [ERROR] Dependency conflict detected in the isolated build environment.
    goto :failed
)

rem ------------------------------------------------------------
rem 4) Install the separate AI runtime into a target folder.
rem    It is NOT embedded in the main EXE. Exact direct versions and
rem    Python 3.12 wheels keep the runtime ABI aligned with the EXE.
echo.
echo [4/9] Building the separate Python 3.12 AI runtime ...
if exist "%AI_DIR%" rmdir /s /q "%AI_DIR%"
mkdir "%AI_DIR%"
(
 echo faster-whisper==1.2.1
 echo ctranslate2==4.8.5
 echo onnxruntime==1.31.1
 echo huggingface-hub==0.36.2
 echo numpy==2.5.4
) > "%BUILD_DIR%\local-ai-constraints.txt"
"%PY%" -m pip install --disable-pip-version-check --target "%AI_DIR%" -r requirements-ai.txt -c "%BUILD_DIR%\local-ai-constraints.txt"
if errorlevel 1 (
    echo [ERROR] Creating the separate AI runtime failed.
    goto :failed
)
"%PY%" -c "import sys; sys.path.insert(0, r'%AI_DIR%'); import asyncio, ctypes.wintypes, faster_whisper, ctranslate2, onnxruntime; print('AI imports OK | faster-whisper', faster_whisper.__version__ if hasattr(faster_whisper,'__version__') else 'loaded', '| ctranslate2', ctranslate2.__version__, '| onnxruntime', onnxruntime.__version__)"
if errorlevel 1 (
    echo [ERROR] AI runtime import test failed before compiling the EXE.
    goto :failed
)
echo local-build> "%AI_DIR%\.hmz_ai_runtime_ready"

rem ------------------------------------------------------------
rem 5) Resolve compiler. Prefer MSVC; otherwise use Nuitka's MinGW64
rem    on Python 3.12. No GitHub Actions dependency.
echo.
echo [5/9] Checking C compiler ...
set "CC_ARG="
set "VS_PATH="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
    for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS_PATH=%%i"
)
if defined VS_PATH (
    echo MSVC Build Tools found.
    set "CC_ARG=--msvc=latest"
) else (
    echo MSVC not found. Nuitka will use MinGW64 ^(first build needs internet^).
    set "CC_ARG=--mingw64"
)

rem ------------------------------------------------------------
rem 6) Version/configuration.
echo.
echo [6/9] Preparing version and application configuration ...
for /f "delims=" %%v in ('"%PY%" tools\print_version.py') do set "APP_VER=%%v"
for /f "delims=" %%v in ('"%PY%" tools\print_version.py --four') do set "FILE_VER=%%v"
if not defined APP_VER (
    echo [ERROR] Could not read application version.
    goto :failed
)
if not defined FILE_VER (
    echo [ERROR] Could not read Windows file version.
    goto :failed
)
rem Keep the repository configurable for the app's online AI-runtime installer.
rem Leave HMZ_AI_REPOSITORY empty for a local/offline build.
"%PY%" -c "import json,os; json.dump({'repository':os.environ.get('HMZ_AI_REPOSITORY','').strip()},open('hmz_ai_config.json','w',encoding='utf-8'))"
if errorlevel 1 goto :failed
echo Version: %APP_VER%  File version: %FILE_VER%

rem ------------------------------------------------------------
rem 7) Unit tests before compilation.
rem    Use a clean temporary APPDATA so a previously installed AI runtime
rem    on this PC cannot leak into tests that verify the missing-runtime case.
echo.
echo [7/9] Running unit tests in an isolated user-data folder ...
if exist "%UNIT_TEST_APPDATA%" rmdir /s /q "%UNIT_TEST_APPDATA%"
mkdir "%UNIT_TEST_APPDATA%"
if errorlevel 1 goto :failed
set "OLD_APPDATA=%APPDATA%"
set "APPDATA=%UNIT_TEST_APPDATA%"
set "QT_QPA_PLATFORM=offscreen"
"%PY%" -m pytest -q tests
set "TEST_EXIT=%ERRORLEVEL%"
set "APPDATA=%OLD_APPDATA%"
set "QT_QPA_PLATFORM="
if not "%TEST_EXIT%"=="0" (
    echo [ERROR] Unit tests failed. Build stopped.
    goto :failed
)

rem ------------------------------------------------------------
rem 8) Compile the lean EXE. asyncio and ctypes.wintypes are explicit
rem    because external AI wheels import these stdlib modules lazily.
echo.
echo [8/9] Compiling the single-file EXE with Nuitka ...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%BUILD_DIR%"
mkdir "%DIST_DIR%"
rem The AI target is recreated after cleaning build; preserve it temporarily.
mkdir "%BUILD_DIR%\ai_runtime"
"%PY%" -c "import os,shutil; shutil.copytree(r'%AI_DIR%',r'%BUILD_DIR%\ai_runtime',dirs_exist_ok=True)"
if errorlevel 1 (
    echo [ERROR] Could not restore the prepared AI runtime after cleaning build.
    goto :failed
)

"%PY%" -m nuitka ^
  --onefile ^
  --enable-plugin=pyqt6 ^
  --include-qt-plugins=sensible,multimedia ^
  --windows-console-mode=disable ^
  --output-dir=build ^
  --output-filename=%APP_NAME%.exe ^
  --company-name="HMZ-Bytes" ^
  --product-name="HMZ Video Studio Pro" ^
  --file-description="HMZ Video Studio Pro" ^
  --file-version=%FILE_VER% ^
  --product-version=%FILE_VER% ^
  --onefile-tempdir-spec="{CACHE_DIR}/HMZ-Bytes/VideoStudioPro/{VERSION}" ^
  --include-module=video_studio_guide_more ^
  --include-module=video_studio_record ^
  --include-module=video_studio_home ^
  --include-module=video_studio_recent ^
  --include-module=video_studio_ai_runtime ^
  --include-module=video_studio_stabilization ^
  --include-package=arabic_reshaper ^
  --include-package=bidi ^
  --include-package=asyncio ^
  --include-module=ctypes.wintypes ^
  --nofollow-import-to=tests ^
  --nofollow-import-to=tools ^
  --nofollow-import-to=pytest ^
  --nofollow-import-to=tkinter ^
  --assume-yes-for-downloads ^
  --remove-output ^
  --include-data-files=hmz_ai_config.json=hmz_ai_config.json ^
  --windows-icon-from-ico=icon.ico ^
  --include-data-files=icon.ico=icon.ico ^
  %CC_ARG% ^
  %ENTRY%
if errorlevel 1 (
    echo [ERROR] Nuitka compilation failed.
    goto :failed
)
if not exist "%BUILD_DIR%\%APP_NAME%.exe" (
    echo [ERROR] Nuitka did not produce the expected EXE.
    goto :failed
)
copy /y "%BUILD_DIR%\%APP_NAME%.exe" "%DIST_DIR%\%APP_NAME%.exe" >nul
if errorlevel 1 goto :failed

rem ------------------------------------------------------------
rem 9) Package runtime and test the actual compiled EXE against it.
echo.
echo [9/9] Packaging AI runtime and testing the compiled EXE ...
"%PY%" -c "import os,zipfile; root=r'%AI_DIR%'; out=r'%DIST_DIR%\HMZ_AI_Runtime_Windows_Py312.zip'; z=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6); [(z.write(os.path.join(dp,f),os.path.relpath(os.path.join(dp,f),root))) for dp,ds,fs in os.walk(root) for f in fs]; z.close()"
if errorlevel 1 goto :failed

if exist "%TEST_APPDATA%" rmdir /s /q "%TEST_APPDATA%"
mkdir "%TEST_APPDATA%\HMZVideoStudioPro\ai_runtime"
"%PY%" -c "import shutil; shutil.copytree(r'%AI_DIR%',r'%TEST_APPDATA%\HMZVideoStudioPro\ai_runtime',dirs_exist_ok=True)"
if errorlevel 1 goto :failed

if exist "%SELFTEST_FILE%" del /q "%SELFTEST_FILE%"
set "OLD_APPDATA=%APPDATA%"
set "APPDATA=%TEST_APPDATA%"
"%DIST_DIR%\%APP_NAME%.exe" --selftest --require-ai --selftest-out "%SELFTEST_FILE%"
set "EXE_EXIT=%ERRORLEVEL%"
set "APPDATA=%OLD_APPDATA%"
if not exist "%SELFTEST_FILE%" (
    echo [ERROR] Compiled EXE did not produce its AI self-test report. Exit code: %EXE_EXIT%
    goto :failed
)
type "%SELFTEST_FILE%"
findstr /b /c:"RESULT PASS" "%SELFTEST_FILE%" >nul
if errorlevel 1 (
    echo [ERROR] The compiled EXE failed its self-test with the external AI runtime.
    goto :failed
)

certutil -hashfile "%DIST_DIR%\%APP_NAME%.exe" SHA256 > "%DIST_DIR%\SHA256.txt"
if errorlevel 1 goto :failed
"%PY%" -c "import hashlib,pathlib; p=pathlib.Path(r'%DIST_DIR%\HMZ_AI_Runtime_Windows_Py312.zip'); h=hashlib.sha256(p.read_bytes()).hexdigest(); pathlib.Path(r'%DIST_DIR%\HMZ_AI_Runtime_Windows_Py312.sha256').write_text(h+'  '+p.name+'\n',encoding='ascii')"
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo [SUCCESS] Local build completed. EXE + AI runtime self-test passed.
echo EXE: %DIST_DIR%\%APP_NAME%.exe
echo AI : %DIST_DIR%\HMZ_AI_Runtime_Windows_Py312.zip
echo Python used: 3.12 x64 in .hmz_build_venv
echo ============================================================
echo NOTE: The AI runtime ZIP is a separate package; it is not embedded in the EXE.
echo For online in-app AI runtime download, set HMZ_AI_REPOSITORY to owner/repository
echo when building and publish the runtime ZIP plus its SHA256 sidecar as release assets.
endlocal
exit /b 0

:failed
echo.
echo ============================================================
echo [FAILED] Local build stopped. Review the FIRST error above.
echo No successful build is being reported.
echo ============================================================
endlocal
exit /b 1
