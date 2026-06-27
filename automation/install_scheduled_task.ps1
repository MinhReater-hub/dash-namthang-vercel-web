[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Projects\dash-namthang-fresh",
    [string]$TaskName = "Dashboard NamThang - Daily Refresh",
    [string]$RunAt = "10:10",
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$automationScript = Join-Path $RepoPath "automation\update_dashboard_daily.ps1"
if (-not (Test-Path -LiteralPath $automationScript -PathType Leaf)) {
    throw "Không tìm thấy script: $automationScript"
}

try {
    $scheduledTime = [DateTime]::ParseExact($RunAt, "HH:mm", $null)
}
catch {
    throw "RunAt phải có dạng HH:mm, ví dụ 10:10."
}

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
$isAdministrator = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdministrator) {
    Write-Warning "Nên chạy PowerShell bằng Run as administrator để cài task ổn định."
}

$powerShellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -RepoPath "{1}"' -f $automationScript, $RepoPath

$action = New-ScheduledTaskAction `
    -Execute $powerShellExe `
    -Argument $arguments `
    -WorkingDirectory $RepoPath

$trigger = New-ScheduledTaskTrigger -Daily -At $scheduledTime

$userId = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90) `
    -MultipleInstances IgnoreNew

$description = "Tự động lấy SQL, kiểm tra cache, commit và push GitHub cho dashboard lúc $RunAt hằng ngày."

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description $description | Out-Null

Write-Host ""
Write-Host "Đã tạo Task Scheduler thành công."
Write-Host "Tên task : $TaskName"
Write-Host "Giờ chạy : $RunAt hằng ngày"
Write-Host "Tài khoản : $userId"
Write-Host "Script    : $automationScript"
Write-Host ""
Write-Host "Task hiện chạy khi tài khoản Windows đang đăng nhập."
Write-Host "Muốn chạy khi đã đăng xuất: mở Task Scheduler, chọn task,"
Write-Host "đổi sang 'Run whether user is logged on or not' và nhập mật khẩu Windows."

if ($RunNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host ""
    Write-Host "Đã yêu cầu chạy thử task ngay."
}
