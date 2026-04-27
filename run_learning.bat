@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [Warren] 학습 에이전트 시작 %date% %time%
python core\learning_agent.py
echo [Warren] 학습 완료 %time%
