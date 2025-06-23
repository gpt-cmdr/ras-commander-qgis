@echo off
REM run_tests_with_qgis_env.bat
REM Sets up QGIS environment and runs tests

set OSGEO4W_ROOT=C:\Program Files\QGIS 3.42.3
set QGIS_PREFIX_PATH=%OSGEO4W_ROOT%\apps\qgis
set PATH=%OSGEO4W_ROOT%\bin;%OSGEO4W_ROOT%\apps\qgis\bin;%PATH%

REM Set Python paths
set PYTHONHOME=%OSGEO4W_ROOT%\apps\Python312
set PYTHONPATH=%OSGEO4W_ROOT%\apps\qgis\python;%OSGEO4W_ROOT%\apps\qgis\python\plugins;%OSGEO4W_ROOT%\apps\Python312\lib\site-packages;%PYTHONPATH%

REM Set Qt plugin path
set QT_PLUGIN_PATH=%OSGEO4W_ROOT%\apps\qgis\qtplugins;%OSGEO4W_ROOT%\apps\qt5\plugins

REM Call QGIS environment setup if it exists
if exist "%OSGEO4W_ROOT%\bin\qgis-bin-env.bat" call "%OSGEO4W_ROOT%\bin\qgis-bin-env.bat"
if exist "%OSGEO4W_ROOT%\bin\py3_env.bat" call "%OSGEO4W_ROOT%\bin\py3_env.bat"
if exist "%OSGEO4W_ROOT%\bin\qt5_env.bat" call "%OSGEO4W_ROOT%\bin\qt5_env.bat"

REM Now run the test suite
echo Running RAS Commander test suite with QGIS environment...
echo.

REM Use the Python from OSGEO4W bin
"%OSGEO4W_ROOT%\bin\python.exe" --version
echo.

REM Run the actual test script
call test_all_algorithms.bat

pause