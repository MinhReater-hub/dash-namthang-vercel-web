@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo CAP NHAT CODE VA DU LIEU DASHBOARD LEN GITHUB
echo ==========================================
echo.

git switch main
if errorlevel 1 goto :error

git pull --rebase origin main
if errorlevel 1 goto :error

git add .
if errorlevel 1 goto :error

git diff --cached --quiet
if %errorlevel%==0 (
    echo.
    echo Khong co thay doi moi de commit.
    goto :done
)

git commit -m "Update dashboard app and data"
if errorlevel 1 goto :error

git push origin main
if errorlevel 1 goto :error

echo.
echo Da cap nhat code va du lieu dashboard len GitHub thanh cong.
goto :done

:error
echo.
echo Co loi xay ra. Hay xem thong bao phia tren.
echo.

:done
pause
endlocal
