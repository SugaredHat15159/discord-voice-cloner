@echo off
cd /d "%~dp0"
set "PY="
for %%P in (
  "%USERPROFILE%\anaconda3\envs\discord-voice-cloner\python.exe"
  "%USERPROFILE%\miniconda3\envs\discord-voice-cloner\python.exe"
  "%LOCALAPPDATA%\anaconda3\envs\discord-voice-cloner\python.exe"
  "C:\ProgramData\anaconda3\envs\discord-voice-cloner\python.exe"
) do if exist %%~P set "PY=%%~P"
if not defined PY ( echo Env not found. Run install.bat first. & pause & exit /b 1 )
"%PY%" run.py
pause