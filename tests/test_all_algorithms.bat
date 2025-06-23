@echo off
REM test_all_algorithms.bat
REM Tests all RAS Commander algorithms individually

setlocal enabledelayedexpansion

REM Set Python path - Use QGIS Python from bin directory for proper environment
set PYTHON_PATH="C:\Program Files\QGIS 3.42.3\bin\python.exe"

if not exist %PYTHON_PATH% (
    echo ERROR: Could not find QGIS Python at %PYTHON_PATH%
    echo Please check your QGIS installation and update this script.
    pause
    exit /b 1
)

echo Using Python: %PYTHON_PATH%

REM Clear previous results
if exist test_results (
    rmdir /s /q test_results
)
mkdir test_results

REM Define all algorithms to test
set ALGORITHMS=load_1d_cross_sections load_1d_river_centerlines load_1d_bank_lines load_1d_hydraulic_structures load_1d_xsec_results
set ALGORITHMS=%ALGORITHMS% load_2d_mesh_area_perimeters load_2d_mesh_cells load_2d_mesh_cell_faces load_2d_mesh_cell_points
set ALGORITHMS=%ALGORITHMS% load_2d_breaklines load_2d_boundary_condition_lines
set ALGORITHMS=%ALGORITHMS% load_2d_maximum_water_surface_points load_2d_maximum_iteration_count_points load_2d_minimum_water_surface_points
set ALGORITHMS=%ALGORITHMS% load_2d_max_face_velocity_points load_2d_max_courant_points
set ALGORITHMS=%ALGORITHMS% load_pipe_conduits load_pipe_nodes
set ALGORITHMS=%ALGORITHMS% load_plan_parameters load_runtime_statistics load_volume_accounting
set ALGORITHMS=%ALGORITHMS% delineate_fluvial_pluvial_boundary analyze_benefit_areas

REM Test each algorithm
echo.
echo ========================================
echo RAS Commander Algorithm Test Suite
echo ========================================
echo.

set /a total=0
set /a passed=0
set /a failed=0
set /a crashed=0

for %%A in (%ALGORITHMS%) do (
    set /a total+=1
    echo Testing %%A...
    
    REM Run test in separate process
    %PYTHON_PATH% test_single_algorithm.py %%A > test_results\%%A.log 2>&1
    
    REM Check exit code
    if !errorlevel! equ 0 (
        echo   [PASS] %%A
        set /a passed+=1
    ) else if !errorlevel! equ 2 (
        echo   [CRASH] %%A - Check test_results\%%A.log for details
        set /a crashed+=1
    ) else (
        echo   [FAIL] %%A - Check test_results\%%A.log for details
        set /a failed+=1
    )
    
    REM Move result file
    if exist test_result_%%A.json (
        move test_result_%%A.json test_results\ >nul
    )
    echo.
)

REM Summary
echo ========================================
echo Test Summary
echo ========================================
echo Total:   %total%
echo Passed:  %passed%
echo Failed:  %failed%
echo Crashed: %crashed%
echo.
echo Detailed results in test_results\ folder
echo ========================================

REM Create summary file
(
echo Test Summary
echo ============
echo Total:   %total%
echo Passed:  %passed%
echo Failed:  %failed%
echo Crashed: %crashed%
echo.
echo Crashed Algorithms:
for %%A in (%ALGORITHMS%) do (
    %PYTHON_PATH% -c "import json; r=json.load(open('test_results/test_result_%%A.json')); exit(0 if r.get('status')!='crashed' else 1)" 2>nul
    if !errorlevel! neq 0 echo   - %%A
)
echo.
echo Failed Algorithms:
for %%A in (%ALGORITHMS%) do (
    %PYTHON_PATH% -c "import json; r=json.load(open('test_results/test_result_%%A.json')); exit(0 if r.get('status')!='failed' else 1)" 2>nul
    if !errorlevel! neq 0 echo   - %%A
)
) > test_results\summary.txt

type test_results\summary.txt

pause