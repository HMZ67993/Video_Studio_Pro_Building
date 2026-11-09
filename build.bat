@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title HMZ Video Studio Pro - Build (Nuitka single-file EXE)

set "APP_NAME=HMZVideoStudioPro"
set "ENTRY=video_studio.py"

echo ============================================================
echo  HMZ Video Studio Pro - single-file EXE build (Nuitka)
echo ============================================================

rem ---------------------------------------------------------------- 1. Python
echo [1/8] Checking Python ...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH. Install Python 3.12 from python.org and tick "Add to PATH".
    goto :err
)
python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required. Python 3.12 is recommended.
    goto :err
)
python -c "import struct,sys; sys.exit(0 if struct.calcsize('P')*8 == 64 else 1)"
if errorlevel 1 (
    echo [ERROR] 64-bit Python is required.
    goto :err
)
python -c "import sys; print('       Python', sys.version.split()[0])"

rem ---------------------------------------------------------------- 2. deps
echo [2/8] Installing dependencies from requirements.txt ...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :err
rem AI runtime is downloaded on demand by the app; keep the main EXE small.
set "AI_SELFTEST_ARG="
python -c "import json,os; json.dump({'repository':os.environ.get('HMZ_AI_REPOSITORY','')},open('hmz_ai_config.json','w',encoding='utf-8'))"

rem ---------------------------------------------------------------- 3. Nuitka + compiler
echo [3/8] Checking Nuitka and the C compiler ...
python -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Nuitka is not installed correctly. Run: python -m pip install nuitka ordered-set zstandard
    goto :err
)
set "CC_ARG="
set "VS_PATH="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :no_msvc
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS_PATH=%%i"
if not defined VS_PATH goto :no_msvc
echo        Found Visual Studio C++ build tools.
set "CC_ARG=--msvc=latest"
goto :cc_done

:no_msvc
python -c "import sys; sys.exit(0 if sys.version_info[:2] <= (3, 12) else 1)"
if errorlevel 1 goto :need_msvc
echo [WARN] MSVC not found. Nuitka will download MinGW64 automatically ^(internet required, first build only^).
set "CC_ARG=--mingw64"
goto :cc_done

:need_msvc
echo [ERROR] Python 3.13 or newer needs Visual Studio Build Tools ^(Desktop development with C++^). Install them or use Python 3.12.
goto :err

:cc_done

rem ---------------------------------------------------------------- 4. version + icon
echo [4/8] Reading version and icon ...
for /f "delims=" %%v in ('python tools\print_version.py') do set "APP_VER=%%v"
for /f "delims=" %%v in ('python tools\print_version.py --four') do set "FILE_VER=%%v"
if not defined APP_VER (
    echo [ERROR] Could not read APP_VERSION from video_studio_i18n.py
    goto :err
)
echo        Version %APP_VER% ^(file version %FILE_VER%^)
set "ICON_ARGS="
if exist "icon.ico" (
    echo        icon.ico found - embedding application and window icon.
    set "ICON_ARGS=--windows-icon-from-ico=icon.ico --include-data-files=icon.ico=icon.ico"
) else (
    echo [ERROR] Required icon.ico not found next to build.bat.
    echo         Add icon.ico to the project root before building.
    goto :err
)

rem ---------------------------------------------------------------- 5. tests (fast, no GUI needed)
echo [5/8] Running unit tests ...
set "QT_QPA_PLATFORM=offscreen"
python -m pytest -q tests
if errorlevel 1 (
    echo [ERROR] Tests failed - fix them before building a release.
    goto :err
)
set "QT_QPA_PLATFORM="

rem ---------------------------------------------------------------- 6. build
echo [6/8] Compiling ^(this takes several minutes the first time^) ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
mkdir dist
python -m nuitka ^
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
  --nofollow-import-to=tests ^
  --nofollow-import-to=tools ^
  --nofollow-import-to=pytest ^
  --nofollow-import-to=tkinter ^
  --assume-yes-for-downloads ^
  --remove-output ^
  --include-data-files=hmz_ai_config.json=hmz_ai_config.json ^
  %CC_ARG% ^
  %ICON_ARGS% ^
  %ENTRY%
if errorlevel 1 goto :err
if not exist "build\%APP_NAME%.exe" (
    echo [ERROR] Nuitka finished but build\%APP_NAME%.exe was not created.
    goto :err
)
copy /y "build\%APP_NAME%.exe" "dist\%APP_NAME%.exe" >nul
if errorlevel 1 goto :err

rem ---------------------------------------------------------------- 7. optional signing, manifest, hash
echo [7/8] Signing / hashing ...
if not defined SIGN_PFX goto :no_sign
if not defined SIGN_PASSWORD goto :sign_pw_missing
signtool sign /f "%SIGN_PFX%" /p "%SIGN_PASSWORD%" /fd sha256 /tr http://timestamp.digicert.com /td sha256 "dist\%APP_NAME%.exe"
if errorlevel 1 goto :err
signtool verify /pa "dist\%APP_NAME%.exe"
if errorlevel 1 goto :err
echo        Authenticode signature verified.
goto :sign_done

:sign_pw_missing
echo [ERROR] SIGN_PFX is set but SIGN_PASSWORD is not. Set both as environment variables, never inside the project.
goto :err

:no_sign
echo [WARN] No code-signing certificate configured ^(SIGN_PFX^). The EXE is UNSIGNED - Windows SmartScreen may warn users.

:sign_done
if not exist "tools\keys\manifest.key" goto :no_manifest
python tools\issue_serial.py manifest --dir dist
if errorlevel 1 goto :err
goto :manifest_done

:no_manifest
echo [INFO] tools\keys\manifest.key not found - skipping integrity.json ^(optional for the single-file build^).

:manifest_done
certutil -hashfile "dist\%APP_NAME%.exe" SHA256 > "dist\SHA256.txt"
type "dist\SHA256.txt"

rem ---------------------------------------------------------------- 8. real smoke test of the EXE
echo [8/8] Running the built EXE self-test ...
if exist "build\selftest.txt" del /q "build\selftest.txt"
start "" /wait "dist\%APP_NAME%.exe" --selftest %AI_SELFTEST_ARG% --selftest-out "%CD%\build\selftest.txt"
if not exist "build\selftest.txt" (
    echo [ERROR] The EXE produced no self-test result. It probably failed to start - check antivirus and crash.log.
    goto :err
)
type "build\selftest.txt"
findstr /b /c:"RESULT PASS" "build\selftest.txt" >nul
if errorlevel 1 (
    echo [ERROR] Self-test reported failures - a module or Qt plugin is missing from the build.
    goto :err
)

echo ============================================================
echo [SUCCESS] Build completed and self-test passed.
echo Output: %CD%\dist\%APP_NAME%.exe
echo ============================================================
echo Next: test on a clean Windows machine, then run installer.iss with Inno Setup if you want a setup file.
endlocal
exit /b 0

:err
echo ============================================================
echo [FAILED] Build failed. Read the messages above.
echo ============================================================
endlocal
exit /b 1
