[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Projects\dash-namthang-fresh"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Import-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Không tìm thấy file .env: $Path"
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()

        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -lt 1) {
            continue
        }

        $name = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()

        if (
            $value.Length -ge 2 -and
            (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Get-OptionalProperty {
    param(
        [AllowNull()]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

$envPath = Join-Path $RepoPath ".env"
Import-DotEnv -Path $envPath

$token = [Environment]::GetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "Process")
$chatId = [Environment]::GetEnvironmentVariable("TELEGRAM_CHAT_ID", "Process")

if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Chưa có TELEGRAM_BOT_TOKEN trong .env."
}

if ([string]::IsNullOrWhiteSpace($chatId)) {
    Write-Host ""
    Write-Host "Chưa có TELEGRAM_CHAT_ID."
    Write-Host "Mở bot Telegram, bấm Start hoặc gửi một tin nhắn, rồi chạy lại script."
    Write-Host ""
    Write-Host "Đang tìm chat ID từ Telegram..."

    $response = Invoke-RestMethod `
        -Uri "https://api.telegram.org/bot$token/getUpdates" `
        -Method Get `
        -TimeoutSec 20

    $updates = @(Get-OptionalProperty -Object $response -Name "result")
    $candidates = @()

    foreach ($update in $updates) {
        if ($null -eq $update) {
            continue
        }

        $message = Get-OptionalProperty -Object $update -Name "message"

        if ($null -eq $message) {
            $message = Get-OptionalProperty -Object $update -Name "edited_message"
        }

        if ($null -eq $message) {
            $message = Get-OptionalProperty -Object $update -Name "channel_post"
        }

        if ($null -eq $message) {
            continue
        }

        $chat = Get-OptionalProperty -Object $message -Name "chat"
        if ($null -eq $chat) {
            continue
        }

        $firstName = [string](Get-OptionalProperty -Object $chat -Name "first_name")
        $lastName = [string](Get-OptionalProperty -Object $chat -Name "last_name")
        $title = [string](Get-OptionalProperty -Object $chat -Name "title")
        $username = [string](Get-OptionalProperty -Object $chat -Name "username")
        $type = [string](Get-OptionalProperty -Object $chat -Name "type")
        $foundChatId = [string](Get-OptionalProperty -Object $chat -Name "id")

        if ([string]::IsNullOrWhiteSpace($foundChatId)) {
            continue
        }

        $displayName = (
            @($firstName, $lastName, $title) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        ) -join " "

        $candidates += [PSCustomObject]@{
            ChatId = $foundChatId
            Type = $type
            Name = $displayName
            Username = $username
        }
    }

    $uniqueCandidates = @($candidates | Sort-Object ChatId -Unique)

    if ($uniqueCandidates.Count -eq 0) {
        Write-Host ""
        Write-Host "Chưa tìm thấy chat nào."
        Write-Host "Hãy mở đúng bot, gửi /start hoặc hello, chờ vài giây rồi chạy lại."
        exit 1
    }

    Write-Host ""
    $uniqueCandidates | Format-Table -AutoSize
    Write-Host ""
    Write-Host "Thêm dòng sau vào file .env, thay CHAT_ID bằng số đúng ở bảng trên:"
    Write-Host 'TELEGRAM_CHAT_ID="CHAT_ID"'
    exit 0
}

Invoke-RestMethod `
    -Uri "https://api.telegram.org/bot$token/sendMessage" `
    -Method Post `
    -Body @{
        chat_id = $chatId
        text = "✅ Kết nối Telegram thành công.`nDashboard NamThang đã sẵn sàng gửi thông báo tự động."
        disable_web_page_preview = "true"
    } `
    -TimeoutSec 20 | Out-Null

Write-Host "Đã gửi tin nhắn thử nghiệm tới Telegram."
