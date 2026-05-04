# Warren Task Scheduler 등록 — XML 방식 (가장 안정적)
# PowerShell에서 직접 실행: powershell -ExecutionPolicy Bypass -File register_tasks.ps1

$BaseDir = "C:\WarrenTradingActivebot-1.0.0\WarrenTradingActivebot-1.0.0"
$Python  = (python -c "import sys; print(sys.executable)" 2>$null).Trim()
if (-not $Python) { $Python = "python" }

Write-Host "Python: $Python"

# 기존 삭제
"Warren_Master_KR","Warren_Master_US","Warren_Master_Crypto","Warren_Learning_Daily" | ForEach-Object {
    schtasks /delete /tn $_ /f 2>$null | Out-Null
    Write-Host "  삭제: $_"
}

# XML 태스크 생성 함수
function Register-WarrenTask {
    param($Name, $Script, $StartTime, $EndTime, $IntervalMinutes, $Daily=$false)

    $XmlPath = "$env:TEMP\$Name.xml"
    $Author  = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

    if ($Daily) {
        # 1회 반복 (학습 루프)
        $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-04-28T$($StartTime):00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
  </Settings>
  <Actions>
    <Exec>
      <Command>$Python</Command>
      <Arguments>$Script</Arguments>
      <WorkingDirectory>$BaseDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
    } else {
        # 15분 반복
        $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-04-28T$($StartTime):00</StartBoundary>
      <EndBoundary>2026-12-31T23:59:00</EndBoundary>
      <Repetition>
        <Interval>PT$($IntervalMinutes)M</Interval>
        <Duration>PT7H</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <StartWhenAvailable>true</StartWhenAvailable>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
  </Settings>
  <Actions>
    <Exec>
      <Command>$Python</Command>
      <Arguments>$Script</Arguments>
      <WorkingDirectory>$BaseDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
    }

    [System.IO.File]::WriteAllText($XmlPath, $xml, [System.Text.Encoding]::Unicode)
    $result = schtasks /create /tn $Name /xml $XmlPath /f 2>&1
    Remove-Item $XmlPath -ErrorAction SilentlyContinue

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $Name"
    } else {
        Write-Host "[FAIL] $Name : $result"
    }
}

$MasterScript = "$BaseDir\run_master_loop.py"
$LearnScript  = "$BaseDir\run_learning_loop.py"

Write-Host ""
Write-Host "=== Warren Task Scheduler 등록 ==="

# 한국장: 09:00, 15분 반복, 7시간(~16:00)
Register-WarrenTask "Warren_Master_KR"     $MasterScript "09:00" "16:00" 15
# 미국장: 22:30, 15분 반복, 7시간(~05:30)
Register-WarrenTask "Warren_Master_US"     $MasterScript "22:30" "06:00" 15
# 코인 공백: 07:00, 15분 반복, 2시간(~09:00)
Register-WarrenTask "Warren_Master_Crypto" $MasterScript "07:00" "09:00" 15
# 학습: 06:05, 매일 1회
Register-WarrenTask "Warren_Learning_Daily" $LearnScript "06:05" "" 0 $true

Write-Host ""
Write-Host "=== 등록 결과 ==="
schtasks /query /fo TABLE | Select-String "Warren"

Write-Host ""
Write-Host "★ strategy_proposals.json 에 제안 저장됨 (자동 적용 금지)"
Write-Host "★ 즉시 테스트: python $MasterScript"
