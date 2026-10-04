@echo off
title Osu!Mania Player v1.2.3
python mania_gui.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred. Press any key to exit.
    pause >nul
)
