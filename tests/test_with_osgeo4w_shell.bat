@echo off
REM test_with_osgeo4w_shell.bat
REM Uses OSGeo4W shell to run tests with proper environment

set OSGEO4W_ROOT=C:\Program Files\QGIS 3.42.3

REM Check if QGIS is installed
if not exist "%OSGEO4W_ROOT%\bin\qgis-bin.exe" (
    echo ERROR: QGIS not found at %OSGEO4W_ROOT%
    echo Please update OSGEO4W_ROOT in this script
    pause
    exit /b 1
)

REM Run test using OSGeo4W shell
echo Starting tests with OSGeo4W environment...
echo.

if "%1"=="" (
    REM Run all tests
    "%OSGEO4W_ROOT%\OSGeo4W.bat" python test_single_algorithm.py load_1d_cross_sections
) else (
    REM Run specific test
    "%OSGEO4W_ROOT%\OSGeo4W.bat" python test_single_algorithm.py %1
)

pause