@echo off
title Mania Player Calibration Harness
python mania_harness.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred. Press any key to exit.
    pause >nul
)
