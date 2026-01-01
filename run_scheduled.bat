@echo off
REM ============================================================
REM PO Vendor Inquiry - Scheduled Task Runner
REM ============================================================
REM This batch file is designed for Windows Task Scheduler.
REM
REM Setup in Task Scheduler:
REM   1. Create a new task
REM   2. Set trigger: Weekly (e.g., Monday 8:00 AM)
REM   3. Action: Start a program
REM      Program: D:\OneDrive\Projects\data_gather\run_scheduled.bat
REM      Start in: D:\OneDrive\Projects\data_gather
REM   4. Check "Run whether user is logged on or not"
REM ============================================================

cd /d D:\OneDrive\Projects\data_gather

REM Activate virtual environment and run the scheduled script
.venv\Scripts\python.exe src\scheduled_run.py

REM Capture exit code
set EXIT_CODE=%ERRORLEVEL%

REM Exit with the same code
exit /b %EXIT_CODE%
