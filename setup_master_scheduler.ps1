# Warren Master Loop — Task Scheduler 등록
# 관리자 권한으로 실행하거나, 현재 사용자 범위로 등록

$BaseDir    = "C:\WarrenTradingActivebot-1.0.0\WarrenTradingActivebot-1.0.0"
$MasterScript = "$BaseDir\run_master_loop.py"
$LogDir     = "$BaseDir\logs"
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) { $PythonPath = "python" }

Write-Host "============================================================"
Write-Host "  Warren Master Loop Scheduler 등록"
Write-Host "  Python: $PythonPath"
Write-Host "  Script: $MasterScript"
Write-Host "============================================================"

# logs 폴더 생성
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# 기존 태스크 삭제
foreach ($name in @("Warren_Master_KR", "Warren_Master_US", "Warren_Master_Crypto", "Warren_Learning_Daily")) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "  삭제: $name"
    }
}

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# ── 한국장: 09:00~15:45, 15분 간격 ──────────────────────────────
# 매 15분마다 실행하는 트리거 생성 (반복)
$act_kr = New-ScheduledTaskAction -Execute $PythonPath -Argument $MasterScript -WorkingDirectory $BaseDir
$trig_kr = New-ScheduledTaskTrigger -Daily -At "09:00"
$trig_kr.RepetitionInterval = [System.TimeSpan]::FromMinutes(15)
$trig_kr.RepetitionDuration = [System.TimeSpan]::FromHours(7)   # 09:00~16:00

Register-ScheduledTask -TaskName "Warren_Master_KR" `
    -Action $act_kr -Trigger $trig_kr -Settings $Settings -Force | Out-Null
Write-Host "[OK] Warren_Master_KR  — 09:00~16:00, 15분 간격 (한국장)"

# ── 미국장: 22:30~06:00, 15분 간격 ──────────────────────────────
$act_us  = New-ScheduledTaskAction -Execute $PythonPath -Argument $MasterScript -WorkingDirectory $BaseDir
$trig_us = New-ScheduledTaskTrigger -Daily -At "22:30"
$trig_us.RepetitionInterval = [System.TimeSpan]::FromMinutes(15)
$trig_us.RepetitionDuration = [System.TimeSpan]::FromHours(7.5) # 22:30~06:00

Register-ScheduledTask -TaskName "Warren_Master_US" `
    -Action $act_us -Trigger $trig_us -Settings $Settings -Force | Out-Null
Write-Host "[OK] Warren_Master_US  — 22:30~06:00, 15분 간격 (미국장)"

# ── 코인: 07:00~08:45 (KR/US 공백 보완), 15분 간격 ─────────────
$act_cr  = New-ScheduledTaskAction -Execute $PythonPath -Argument $MasterScript -WorkingDirectory $BaseDir
$trig_cr = New-ScheduledTaskTrigger -Daily -At "07:00"
$trig_cr.RepetitionInterval = [System.TimeSpan]::FromMinutes(15)
$trig_cr.RepetitionDuration = [System.TimeSpan]::FromHours(2)   # 07:00~09:00

Register-ScheduledTask -TaskName "Warren_Master_Crypto" `
    -Action $act_cr -Trigger $trig_cr -Settings $Settings -Force | Out-Null
Write-Host "[OK] Warren_Master_Crypto — 07:00~09:00, 15분 간격 (코인 전용)"

# ── 일일 학습 리포트: 매일 06:05 ────────────────────────────────
$LearnScript = "$BaseDir\run_learning_loop.py"
$act_lrn  = New-ScheduledTaskAction -Execute $PythonPath -Argument $LearnScript -WorkingDirectory $BaseDir
$trig_lrn = New-ScheduledTaskTrigger -Daily -At "06:05"
$set_lrn  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable

Register-ScheduledTask -TaskName "Warren_Learning_Daily" `
    -Action $act_lrn -Trigger $trig_lrn -Settings $set_lrn -Force | Out-Null
Write-Host "[OK] Warren_Learning_Daily — 매일 06:05 (학습 + 제안 생성)"

Write-Host ""
Write-Host "============================================================"
Write-Host "  등록된 Warren 태스크 목록:"
Get-ScheduledTask | Where-Object { $_.TaskName -like "Warren_*" } |
    Select-Object TaskName, State |
    Format-Table -AutoSize
Write-Host "============================================================"
Write-Host ""
Write-Host "  ★ 전략 수정 제안은 logs\strategy_proposals.json 에 저장됨"
Write-Host "  ★ 자동 적용 절대 금지 — Claude Code와 논의 후 수동 승인"
Write-Host ""
Write-Host "즉시 테스트: python $MasterScript"
