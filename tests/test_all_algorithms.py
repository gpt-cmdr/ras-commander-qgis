#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run all RAS Commander algorithm tests.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

# Define all algorithms to test
ALGORITHMS = [
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
]

def run_algorithm_test(algorithm_id):
    """Run a single algorithm test."""
    print(f"Testing {algorithm_id}...", end='', flush=True)
    
    # Run test in subprocess
    cmd = [sys.executable, "test_single_algorithm.py", algorithm_id]
    
    try:
        # Create log files
        log_file = f"test_results/{algorithm_id}.log"
        error_file = f"test_results/{algorithm_id}.error.log"
        
        with open(log_file, 'w') as out, open(error_file, 'w') as err:
            result = subprocess.run(cmd, stdout=out, stderr=err, timeout=60)
        
        # Check result
        if result.returncode == 0:
            print(" [PASS]")
            return 'passed'
        elif result.returncode == 2:
            print(" [CRASH]")
            return 'crashed'
        else:
            print(" [FAIL]")
            return 'failed'
            
    except subprocess.TimeoutExpired:
        print(" [TIMEOUT]")
        return 'timeout'
    except Exception as e:
        print(f" [ERROR: {e}]")
        return 'error'

def main():
    """Run all tests and generate summary."""
    print("="*60)
    print("RAS Commander Algorithm Test Suite")
    print("="*60)
    print()
    
    # Create results directory
    os.makedirs("test_results", exist_ok=True)
    
    # Run tests
    results = {
        'passed': [],
        'failed': [],
        'crashed': [],
        'timeout': [],
        'error': []
    }
    
    for algorithm in ALGORITHMS:
        status = run_algorithm_test(algorithm)
        results[status].append(algorithm)
    
    # Print summary
    print()
    print("="*60)
    print("Test Summary")
    print("="*60)
    print(f"Total:    {len(ALGORITHMS)}")
    print(f"Passed:   {len(results['passed'])}")
    print(f"Failed:   {len(results['failed'])}")
    print(f"Crashed:  {len(results['crashed'])}")
    print(f"Timeout:  {len(results['timeout'])}")
    print(f"Error:    {len(results['error'])}")
    
    if results['crashed']:
        print("\nCrashed Algorithms:")
        for alg in results['crashed']:
            print(f"  - {alg}")
    
    if results['failed']:
        print("\nFailed Algorithms:")
        for alg in results['failed']:
            print(f"  - {alg}")
    
    print(f"\nDetailed results in test_results/ folder")
    print("="*60)
    
    # Write summary file
    summary = {
        'total': len(ALGORITHMS),
        'results': results,
        'summary': {
            'passed': len(results['passed']),
            'failed': len(results['failed']),
            'crashed': len(results['crashed']),
            'timeout': len(results['timeout']),
            'error': len(results['error'])
        }
    }
    
    with open('test_results/summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

if __name__ == '__main__':
    main()