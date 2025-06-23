@echo off
REM Test if Python path is correct

echo Testing Python paths...
echo.

REM Test QGIS Python
echo Testing QGIS Python:
"C:\Program Files\QGIS 3.38.3\apps\Python39\python.exe" --version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: QGIS Python not found at expected location
    echo Trying alternative location...
    "C:\OSGeo4W\apps\Python39\python.exe" --version
)

echo.
echo Testing Python execution:
"C:\Program Files\QGIS 3.38.3\apps\Python39\python.exe" -c "import sys; print('Python path:', sys.executable)"

echo.
echo Current directory:
cd

pause