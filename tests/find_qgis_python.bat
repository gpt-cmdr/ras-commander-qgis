@echo off
echo Finding QGIS Python...
echo.

set QGIS_PATH="C:\Program Files\QGIS 3.42.3"

echo Checking in %QGIS_PATH%\apps\
dir %QGIS_PATH%\apps\ | findstr Python

echo.
echo Checking for python.exe:
where /r %QGIS_PATH% python.exe

pause