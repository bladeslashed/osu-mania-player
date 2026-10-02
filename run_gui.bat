@echo off
title osu!mania Player Pro V1.0
python mania_gui.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred. Press any key to exit.
    pause >nul
)
