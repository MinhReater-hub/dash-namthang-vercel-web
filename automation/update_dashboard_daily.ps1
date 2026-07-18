[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Projects\dash-namthang-fresh",
    [string]$PythonLauncher = "py",
    [string]$PythonVersion = "-3.11",
    [int]$LogRetentionDays = 30
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$StateRoot = Join-Path $env:LOCALAPPDATA "DashNamThangAutomation"
$LogRoot = Join-Path $StateRoot "logs"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

$RunStarted = Get-Date
$RunStamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$LogFile = Join-Path $LogRoot "update_$RunStamp.log"
$RefreshStartedUtc = $null
$Mutex = $null
$LockAcquired = $false

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Message,

        [ValidateSet("INFO", "WARN", "ERROR", "CMD")]
        [string]$Level = "INFO"
    )

    # Một số chương trình native (đặc biệt Python/Git) có thể trả về
    # dòng trống trong mảng output. Không coi dòng trống là lỗi.
    if ([string]::IsNullOrWhiteSpace($Message)) {
        return
    }

    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Import-DotEnv {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Không tìm thấy file .env: $Path"
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) { continue }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -lt 1) { continue }

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

function Send-Telegram {
    param([Parameter(Mandatory = $true)][string]$Text)

    $token = [Environment]::GetEnvironmentVariable("TELEGRAM_BOT_TOKEN", "Process")
    $chatId = [Environment]::GetEnvironmentVariable("TELEGRAM_CHAT_ID", "Process")

    if ([string]::IsNullOrWhiteSpace($token) -or [string]::IsNullOrWhiteSpace($chatId)) {
        Write-Log "Chưa có TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID; bỏ qua Telegram." "WARN"
        return
    }

    try {
        Invoke-RestMethod `
            -Uri "https://api.telegram.org/bot$token/sendMessage" `
            -Method Post `
            -Body @{
                chat_id = $chatId
                text = $Text
                disable_web_page_preview = "true"
            } `
            -TimeoutSec 20 | Out-Null
    }
    catch {
        Write-Log "Không gửi được Telegram: $($_.Exception.Message)" "WARN"
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$StepName,
        [int[]]$AllowedExitCodes = @(0)
    )

    Write-Log "$FilePath $($Arguments -join ' ')" "CMD"

    # Git thường ghi các thông báo bình thường như "From https://..."
    # ra stderr. Với Windows PowerShell + ErrorActionPreference=Stop,
    # những dòng này có thể bị hiểu nhầm là lỗi kết thúc script.
    # Tạm chuyển về Continue và chỉ đánh giá kết quả bằng exit code.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    foreach ($item in @($output)) {
        if ($null -eq $item) {
            continue
        }

        $outputLine = [string]$item
        if ([string]::IsNullOrWhiteSpace($outputLine)) {
            continue
        }

        Write-Log -Message $outputLine -Level "CMD"
    }

    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "$StepName thất bại, exit code $exitCode."
    }

    return @($output)
}

function Get-StatusPath {
    param([Parameter(Mandatory = $true)][string]$StatusLine)

    if ($StatusLine.Length -le 3) { return "" }
    $path = $StatusLine.Substring(3).Trim().Trim('"')
    if ($path.Contains(" -> ")) {
        $path = ($path -split " -> ")[-1].Trim().Trim('"')
    }
    return $path.Replace("\", "/")
}

function Assert-NoManualChanges {
    $statusLines = @(& git status --porcelain=v1 --untracked-files=all 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Không đọc được trạng thái Git." }

    $unexpected = @()
    foreach ($line in $statusLines) {
        $text = [string]$line
        if ([string]::IsNullOrWhiteSpace($text)) { continue }

        $path = Get-StatusPath -StatusLine $text
        $allowed =
            $path -eq "output/bao_cao_doanh_thu_tong_hop.xlsx" -or
            $path.StartsWith("output/cache/")

        if (-not $allowed) { $unexpected += $text }
    }

    if ($unexpected.Count -gt 0) {
        throw "Repo đang có file sửa thủ công. Automation dừng để tránh ghi đè:`n$($unexpected -join "`n")"
    }
}

function Restore-GeneratedFiles {
    & git reset --quiet 2>$null
    & git restore --worktree -- "output/bao_cao_doanh_thu_tong_hop.xlsx" 2>$null
    & git restore --worktree -- "output/cache" 2>$null
}

function Clear-GeneratedCache {
    $cachePath = Join-Path $RepoPath "output\cache"
    if (Test-Path -LiteralPath $cachePath) {
        Remove-Item -LiteralPath $cachePath -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $cachePath | Out-Null
}

function Remove-UnusedTop10Caches {
    $cacheRoot = Join-Path $RepoPath "output\cache"

    if (-not (Test-Path -LiteralPath $cacheRoot -PathType Container)) {
        return
    }

    $top10Files = @(
        Get-ChildItem `
            -LiteralPath $cacheRoot `
            -File `
            -Filter "TOP10_*" `
            -ErrorAction SilentlyContinue
    )

    if ($top10Files.Count -eq 0) {
        return
    }

    foreach ($file in $top10Files) {
        Remove-Item -LiteralPath $file.FullName -Force
    }

    Write-Log "Đã loại $($top10Files.Count) cache TOP10 không còn sử dụng."
}


function Assert-RequiredCaches {
    $requiredCaches = @(
        "DoanhThu_Thang_KhuVuc.pkl.gz",
        "DoanhThu_Ngay_Checker.pkl.gz",
        "DoanhThu_Ngay_TaiXe.pkl.gz",
        "Daily_Driver_Options.pkl.gz",
        "KinhDoanh_DiemTiepThi_KV_Thang.pkl.gz",
        "KinhDoanh_BienBan_KV_Thang.pkl.gz",
        "NhanSu_NhanVien_KV_Thang.pkl.gz",
        "NhanSu_TaiXe_KV_Thang.pkl.gz",
        "PhuongTien_XeTrucThuoc_KV_Ngay.pkl.gz",
        "PhuongTien_XePhanQuyen_KV_Ngay.pkl.gz"
    )

    $cacheRoot = Join-Path $RepoPath "output\cache"
    $problems = @()

    foreach ($fileName in $requiredCaches) {
        $fullPath = Join-Path $cacheRoot $fileName

        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            $problems += "Thiếu: $fileName"
            continue
        }

        $item = Get-Item -LiteralPath $fullPath
        if ($item.Length -le 100) {
            $problems += "File quá nhỏ hoặc rỗng: $fileName ($($item.Length) bytes)"
        }

        if ($null -ne $RefreshStartedUtc -and $item.LastWriteTimeUtc -lt $RefreshStartedUtc.AddMinutes(-1)) {
            $problems += "File không được cập nhật trong lần chạy này: $fileName"
        }
    }

    if ($problems.Count -gt 0) {
        throw "Kiểm tra cache thất bại:`n$($problems -join "`n")"
    }

    $allCacheFiles = @(Get-ChildItem -LiteralPath $cacheRoot -File -Recurse)
    if ($allCacheFiles.Count -lt 10) {
        throw "Số lượng cache bất thường: chỉ có $($allCacheFiles.Count) file."
    }

    $totalMb = [math]::Round((($allCacheFiles | Measure-Object Length -Sum).Sum / 1MB), 2)
    Write-Log "Cache hợp lệ: $($allCacheFiles.Count) file, tổng $totalMb MB."
}

function Assert-OnlyCacheIsStaged {
    $stagedPaths = @(& git -c core.quotepath=false diff --cached --name-only 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Không đọc được danh sách file đã stage." }

    $unexpected = @(
        $stagedPaths |
            ForEach-Object {
                ([string]$_).Trim().Trim('"').Replace("\", "/")
            } |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_) -and
                -not $_.StartsWith("output/cache/")
            }
    )

    if ($unexpected.Count -gt 0) {
        throw "Có file ngoài output/cache bị stage:`n$($unexpected -join "`n")"
    }
}

function Get-GitAheadCount {
    $value = (& git rev-list --count "origin/main..HEAD" 2>&1 | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0) { throw "Không kiểm tra được số commit local chưa push." }
    return [int]$value
}

try {
    Get-ChildItem -LiteralPath $LogRoot -File -Filter "*.log" |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$LogRetentionDays) } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    $Mutex = New-Object System.Threading.Mutex($false, "DashNamThangDailyRefresh")
    $LockAcquired = $Mutex.WaitOne(0, $false)
    if (-not $LockAcquired) {
        Write-Log "Một phiên cập nhật khác đang chạy. Phiên này kết thúc." "WARN"
        exit 2
    }

    Write-Log "Bắt đầu cập nhật dashboard tự động."
    Write-Log "Repo: $RepoPath"

    if (-not (Test-Path -LiteralPath $RepoPath -PathType Container)) {
        throw "Không tìm thấy thư mục repo: $RepoPath"
    }

    Set-Location -LiteralPath $RepoPath

    if (-not (Test-Path -LiteralPath ".\refresh_data.py" -PathType Leaf)) {
        throw "Không tìm thấy refresh_data.py."
    }

    Get-Command git -ErrorAction Stop | Out-Null
    Get-Command $PythonLauncher -ErrorAction Stop | Out-Null
    Import-DotEnv -Path (Join-Path $RepoPath ".env")

    Invoke-Native -FilePath "git" -Arguments @("rev-parse", "--is-inside-work-tree") -StepName "Kiểm tra Git" | Out-Null

    Assert-NoManualChanges
    Restore-GeneratedFiles
    Assert-NoManualChanges

    Invoke-Native -FilePath "git" -Arguments @("pull", "--rebase", "origin", "main") -StepName "Đồng bộ GitHub trước khi cập nhật" | Out-Null

    Clear-GeneratedCache
    $RefreshStartedUtc = [DateTime]::UtcNow
    Write-Log "Bắt đầu chạy refresh_data.py."

    Invoke-Native -FilePath $PythonLauncher -Arguments @($PythonVersion, "refresh_data.py") -StepName "Cập nhật dữ liệu SQL" | Out-Null

    Remove-UnusedTop10Caches
    Assert-RequiredCaches

    & git restore --worktree -- "output/bao_cao_doanh_thu_tong_hop.xlsx" 2>$null

    $trackedStatus = @(& git status --porcelain=v1 --untracked-files=no 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Không đọc được trạng thái Git sau refresh." }

    $nonCacheTrackedChanges = @()
    foreach ($line in $trackedStatus) {
        $text = [string]$line
        if ([string]::IsNullOrWhiteSpace($text)) { continue }
        $path = Get-StatusPath -StatusLine $text
        if (-not $path.StartsWith("output/cache/")) { $nonCacheTrackedChanges += $text }
    }

    if ($nonCacheTrackedChanges.Count -gt 0) {
        throw "refresh_data.py làm thay đổi file ngoài output/cache:`n$($nonCacheTrackedChanges -join "`n")"
    }

    Invoke-Native -FilePath "git" -Arguments @("add", "-A", "-f", "--", "output/cache") -StepName "Stage cache" | Out-Null
    Assert-OnlyCacheIsStaged

    & git diff --cached --quiet -- "output/cache"
    $cacheDiffExitCode = $LASTEXITCODE

    if ($cacheDiffExitCode -eq 0) {
        Write-Log "Không có thay đổi cache; bỏ qua commit."

        $aheadCount = Get-GitAheadCount
        if ($aheadCount -gt 0) {
            Write-Log "Có $aheadCount commit local chưa push; đang push lên GitHub."
            Invoke-Native -FilePath "git" -Arguments @("push", "origin", "main") -StepName "Push commit đang chờ" | Out-Null
        }

        $duration = [math]::Round(((Get-Date) - $RunStarted).TotalMinutes, 1)
        Send-Telegram -Text (
            "ℹ️ Dashboard không có dữ liệu mới.`n`n" +
            "Thời gian: $(Get-Date -Format 'dd/MM/yyyy HH:mm')`n" +
            "Không tạo commit, không deploy lại Vercel.`n" +
            "Thời lượng: $duration phút."
        )

        Write-Log "Hoàn tất: không có dữ liệu thay đổi."
        exit 0
    }

    if ($cacheDiffExitCode -ne 1) {
        throw "Không kiểm tra được thay đổi cache, exit code $cacheDiffExitCode."
    }

    $changedFiles = @(& git -c core.quotepath=false diff --cached --name-only -- "output/cache")
    $changedCount = $changedFiles.Count
    $commitMessage = "Auto update dashboard cache $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

    Invoke-Native -FilePath "git" -Arguments @("commit", "-m", $commitMessage) -StepName "Tạo commit cache" | Out-Null
    Invoke-Native -FilePath "git" -Arguments @("pull", "--rebase", "origin", "main") -StepName "Đồng bộ GitHub trước khi push" | Out-Null
    Invoke-Native -FilePath "git" -Arguments @("push", "origin", "main") -StepName "Push lên GitHub" | Out-Null

    $commitHash = (& git rev-parse --short HEAD 2>&1 | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0) { $commitHash = "không xác định" }

    $duration = [math]::Round(((Get-Date) - $RunStarted).TotalMinutes, 1)
    Send-Telegram -Text (
        "✅ Dashboard cập nhật thành công.`n`n" +
        "Thời gian: $(Get-Date -Format 'dd/MM/yyyy HH:mm')`n" +
        "Commit: $commitHash`n" +
        "Cache thay đổi: $changedCount file`n" +
        "Vercel đã được kích hoạt triển khai.`n" +
        "Thời lượng: $duration phút."
    )

    Write-Log "Cập nhật thành công. Commit: $commitHash. Cache thay đổi: $changedCount file."
    exit 0
}
catch {
    $errorMessage = $_.Exception.Message
    Write-Log $errorMessage "ERROR"

    try {
        Set-Location -LiteralPath $RepoPath

        $rebaseDir = Join-Path $RepoPath ".git\rebase-merge"
        $rebaseApplyDir = Join-Path $RepoPath ".git\rebase-apply"
        if ((Test-Path -LiteralPath $rebaseDir) -or (Test-Path -LiteralPath $rebaseApplyDir)) {
            & git rebase --abort 2>$null
        }

        & git reset --quiet 2>$null
        & git clean -fdx -- "output/cache" 2>$null
        & git restore --worktree -- "output/cache" 2>$null
        & git restore --worktree -- "output/bao_cao_doanh_thu_tong_hop.xlsx" 2>$null
    }
    catch {
        Write-Log "Không thể khôi phục repo sau lỗi: $($_.Exception.Message)" "WARN"
    }

    $duration = [math]::Round(((Get-Date) - $RunStarted).TotalMinutes, 1)
    Send-Telegram -Text (
        "❌ Dashboard cập nhật thất bại.`n`n" +
        "Thời gian: $(Get-Date -Format 'dd/MM/yyyy HH:mm')`n" +
        "Lỗi: $errorMessage`n" +
        "Không push dữ liệu lỗi lên GitHub.`n" +
        "Log: $LogFile`n" +
        "Thời lượng: $duration phút."
    )

    exit 1
}
finally {
    if ($LockAcquired -and $null -ne $Mutex) {
        try { $Mutex.ReleaseMutex() } catch {}
    }
    if ($null -ne $Mutex) { $Mutex.Dispose() }
}
