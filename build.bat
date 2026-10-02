@echo off
echo Compiling Mania Player (Native C) with GCC -O3 Optimization and Stripped Symbols...
gcc -O3 -s -march=native -Wall -o maniaplayer.exe maniaplayer.c -lgdi32 -luser32
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] maniaplayer.exe compiled successfully!
) else (
    echo [ERROR] Compilation failed.
)
pause
