@echo off
title Mania Player Python Engine
python maniaplayer.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred. Press any key to exit.
    pause >nul
)
