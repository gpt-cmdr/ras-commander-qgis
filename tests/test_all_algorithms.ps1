# test_all_algorithms.ps1
# PowerShell script to test all RAS Commander algorithms

# Set Python path - Use QGIS Python from bin directory for proper environment
$PYTHON_PATH = "C:\Program Files\QGIS 3.42.3\bin\python.exe"

if (-not (Test-Path $PYTHON_PATH)) {
    Write-Host "ERROR: QGIS Python not found at $PYTHON_PATH" -ForegroundColor Red
    Write-Host "Please check your QGIS installation and update this script." -ForegroundColor Red
    exit 1
}

# Define algorithms
$algorithms = @(
    # 1D Algorithms
    "load_1d_cross_sections",
    "load_1d_river_centerlines", 
    "load_1d_bank_lines",
    "load_1d_hydraulic_structures",
    "load_1d_xsec_results",
    
    # 2D Geometry
    "load_2d_mesh_area_perimeters",
    "load_2d_mesh_cells",
    "load_2d_mesh_cell_faces",
    "load_2d_mesh_cell_points",
    "load_2d_breaklines",
    "load_2d_boundary_condition_lines",
    
    # 2D Results
    "load_2d_maximum_water_surface_points",
    "load_2d_maximum_iteration_count_points",
    "load_2d_minimum_water_surface_points",
    "load_2d_max_face_velocity_points",
    "load_2d_max_courant_points",
    
    # Pipe Network
    "load_pipe_conduits",
    "load_pipe_nodes",
    
    # Metadata
    "load_plan_parameters",
    "load_runtime_statistics",
    "load_volume_accounting",
    
    # Analysis
    "delineate_fluvial_pluvial_boundary",
    "analyze_benefit_areas"
)

# Clear and create results directory
if (Test-Path "test_results") {
    Remove-Item -Path "test_results" -Recurse -Force
}
New-Item -ItemType Directory -Path "test_results" | Out-Null

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RAS Commander Algorithm Test Suite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$results = @{
    passed = @()
    failed = @()
    crashed = @()
}

foreach ($alg in $algorithms) {
    Write-Host "Testing $alg..." -NoNewline
    
    # Run test
    $process = Start-Process -FilePath $PYTHON_PATH `
        -ArgumentList "test_single_algorithm.py", $alg `
        -RedirectStandardOutput "test_results\$alg.log" `
        -RedirectStandardError "test_results\$alg.error.log" `
        -Wait -PassThru -NoNewWindow
    
    # Check result
    if ($process.ExitCode -eq 0) {
        Write-Host " [PASS]" -ForegroundColor Green
        $results.passed += $alg
    } elseif ($process.ExitCode -eq 2) {
        Write-Host " [CRASH]" -ForegroundColor Red
        $results.crashed += $alg
    } else {
        Write-Host " [FAIL]" -ForegroundColor Yellow
        $results.failed += $alg
    }
    
    # Move result file
    if (Test-Path "test_result_$alg.json") {
        Move-Item "test_result_$alg.json" "test_results\" -Force
    }
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total:   $($algorithms.Count)"
Write-Host "Passed:  $($results.passed.Count)" -ForegroundColor Green
Write-Host "Failed:  $($results.failed.Count)" -ForegroundColor Yellow
Write-Host "Crashed: $($results.crashed.Count)" -ForegroundColor Red

if ($results.crashed.Count -gt 0) {
    Write-Host ""
    Write-Host "Crashed Algorithms:" -ForegroundColor Red
    foreach ($alg in $results.crashed) {
        Write-Host "  - $alg"
    }
}

if ($results.failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Failed Algorithms:" -ForegroundColor Yellow
    foreach ($alg in $results.failed) {
        Write-Host "  - $alg"
    }
}

Write-Host ""
Write-Host "Detailed results in test_results\ folder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Save summary
$summary = @"
Test Summary
============
Total:   $($algorithms.Count)
Passed:  $($results.passed.Count)
Failed:  $($results.failed.Count)
Crashed: $($results.crashed.Count)

Crashed Algorithms:
$($results.crashed | ForEach-Object { "  - $_" } | Out-String)

Failed Algorithms:
$($results.failed | ForEach-Object { "  - $_" } | Out-String)

Passed Algorithms:
$($results.passed | ForEach-Object { "  - $_" } | Out-String)
"@

$summary | Out-File "test_results\summary.txt"

Read-Host "Press Enter to continue..."