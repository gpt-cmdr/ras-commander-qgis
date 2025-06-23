@echo off
REM run_all_tests_osgeo4w.bat
REM Runs all tests using OSGeo4W shell environment

set OSGEO4W_ROOT=C:\Program Files\QGIS 3.42.3
set CURRENT_DIR=%~dp0

REM Check if OSGeo4W.bat exists
if not exist "%OSGEO4W_ROOT%\OSGeo4W.bat" (
    echo ERROR: OSGeo4W.bat not found at %OSGEO4W_ROOT%
    echo Looking for qgis-bin-env.bat instead...
    
    if exist "%OSGEO4W_ROOT%\bin\qgis-bin-env.bat" (
        call "%OSGEO4W_ROOT%\bin\qgis-bin-env.bat"
        cd /d "%CURRENT_DIR%"
        python test_all_algorithms.py
    ) else (
        echo ERROR: Could not find QGIS environment setup scripts
        pause
        exit /b 1
    )
) else (
    REM Change to test directory and run tests
    cd /d "%CURRENT_DIR%"
    call "%OSGEO4W_ROOT%\OSGeo4W.bat" python test_all_algorithms.py
)

pause