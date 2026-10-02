@echo off
echo Compiling Mania Player (Native C) with GCC -O3 Optimization and Stripped Symbols...
gcc -O3 -s -march=native -Wall -o maniaplayer_native.exe maniaplayer.c -lgdi32 -luser32
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] maniaplayer_native.exe compiled successfully!
) else (
    echo [ERROR] Compilation failed.
)
pause
