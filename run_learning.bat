@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [Warren] 복기+학습 에이전트 시작 %date% %time%
echo   1. 25전략 시뮬레이션 (14일 롤링)
echo   2. 5-Pillar 손실 방어 검증
python core\learning_agent.py
echo [Warren] 학습 완료 %time%
