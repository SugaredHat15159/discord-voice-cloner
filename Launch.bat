@echo off
cd /d "%~dp0"
set "PY="
for %%P in (
  "%USERPROFILE%\anaconda3\envs\discord-voice-cloner\pythonw.exe"
  "%USERPROFILE%\miniconda3\envs\discord-voice-cloner\pythonw.exe"
  "%LOCALAPPDATA%\anaconda3\envs\discord-voice-cloner\pythonw.exe"
  "C:\ProgramData\anaconda3\envs\discord-voice-cloner\pythonw.exe"
) do if exist %%~P set "PY=%%~P"
if not defined PY (
  echo Could not find the "discord-voice-cloner" conda environment.
  echo Run install.bat once first.
  pause
  exit /b 1
)
start "" /D "%~dp0" "%PY%" run.py