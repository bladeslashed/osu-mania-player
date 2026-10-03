@echo off
echo ========================================================
echo [1/2] Compiling Native C Engine (maniaplayer_native.exe)...
echo ========================================================
gcc -O3 -s -march=native -Wall -o maniaplayer_native.exe maniaplayer.c -lgdi32 -luser32 -lwinmm
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] maniaplayer_native.exe compiled successfully!
) else (
    echo [ERROR] Native C compilation failed.
)

echo.
echo ========================================================
echo [2/2] Compiling Standalone Python GUI (maniaplayer.exe)...
echo ========================================================
python -m PyInstaller ManiaPlayer.spec --clean -y
if %ERRORLEVEL% EQU 0 (
    if exist dist\maniaplayer.exe (
        move /y dist\maniaplayer.exe .\maniaplayer.exe >nul
        rmdir /s /q dist build >nul 2>&1
        echo [SUCCESS] maniaplayer.exe compiled and updated successfully!
    )
) else (
    echo [WARN] PyInstaller compilation failed or was skipped.
)

echo.
echo All builds complete!
pause

