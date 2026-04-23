@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo CAP NHAT FILE DU LIEU DASHBOARD LEN GITHUB
echo ==========================================
echo.

git switch main
if errorlevel 1 goto :error

git pull --rebase origin main
if errorlevel 1 goto :error

git add output\bao_cao_doanh_thu_tong_hop.xlsx
if errorlevel 1 goto :error

git diff --cached --quiet
if %errorlevel%==0 (
    echo.
    echo Khong co thay doi moi trong file Excel de commit.
    goto :done
)

git commit -m "Update dashboard data"
if errorlevel 1 goto :error

git push origin main
if errorlevel 1 goto :error

echo.
echo Da cap nhat file Excel dashboard len GitHub thanh cong.
goto :done

:error
echo.
echo Co loi xay ra. Hay xem thong bao phia tren.
echo.

:done
pause
endlocal
