@echo off
REM One-time setup for the Discord Voice Cloner (Windows + conda).
echo Creating conda env "discord-voice-cloner" (Python 3.10)...
call conda create -y -n discord-voice-cloner python=3.10
echo Activating and installing requirements...
call conda activate discord-voice-cloner
pip install -r requirements.txt
echo.
echo Done. To run:  conda activate discord-voice-cloner ^&^& python run.py
pause
