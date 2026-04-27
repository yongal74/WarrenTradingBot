# Warren FVG+OB 일일 포워드 테스터 - 스케줄러 등록
# 관리자 권한 없이도 현재 사용자 범위로 등록

$BaseDir = "C:\WarrenTradingActivebot-1.0.0\WarrenTradingActivebot-1.0.0"
$Script  = "$BaseDir\run_forward_daily.py"
$LogDir  = "$BaseDir\logs"

# logs 폴더 생성
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Python 경로 확인
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) { $PythonPath = "python" }
Write-Host "Python: $PythonPath"

# 기존 태스크 삭제
foreach ($name in @("WarrenScan_KR", "WarrenScan_US", "WarrenReport")) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "삭제: $name"
    }
}

# ── 한국장 스캔: 매일 09:00 ──────────────────────────────────
$act_kr  = New-ScheduledTaskAction -Execute $PythonPath -Argument $Script
$trig_kr = New-ScheduledTaskTrigger -Daily -At "09:00"
$set_kr  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
Register-ScheduledTask -TaskName "WarrenScan_KR" `
    -Action $act_kr -Trigger $trig_kr -Settings $set_kr -Force | Out-Null
Write-Host "[OK] WarrenScan_KR  - 매일 09:00 (한국장 시작 스캔)"

# ── 미국장 스캔: 매일 22:30 ──────────────────────────────────
$act_us  = New-ScheduledTaskAction -Execute $PythonPath -Argument $Script
$trig_us = New-ScheduledTaskTrigger -Daily -At "22:30"
$set_us  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
Register-ScheduledTask -TaskName "WarrenScan_US" `
    -Action $act_us -Trigger $trig_us -Settings $set_us -Force | Out-Null
Write-Host "[OK] WarrenScan_US  - 매일 22:30 (미국장 시작 스캔)"

# ── 아침 리포트: 매일 06:10 ──────────────────────────────────
$act_rp  = New-ScheduledTaskAction -Execute $PythonPath -Argument "$Script --report"
$trig_rp = New-ScheduledTaskTrigger -Daily -At "06:10"
$set_rp  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable
Register-ScheduledTask -TaskName "WarrenReport" `
    -Action $act_rp -Trigger $trig_rp -Settings $set_rp -Force | Out-Null
Write-Host "[OK] WarrenReport   - 매일 06:10 (전일 결과 리포트)"

Write-Host ""
Write-Host "============================================================"
Write-Host "  등록된 Warren 태스크:"
Get-ScheduledTask | Where-Object { $_.TaskName -like "Warren*" } |
    Select-Object TaskName, State, @{N="NextRun";E={(Get-ScheduledTaskInfo $_.TaskName).NextRunTime}} |
    Format-Table -AutoSize
Write-Host "============================================================"
Write-Host ""
Write-Host "즉시 테스트: python $Script"
