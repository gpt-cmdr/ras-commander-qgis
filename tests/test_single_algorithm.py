# test_single_algorithm.py
# -*- coding: utf-8 -*-
"""
Test a single RAS Commander algorithm from command line.
Usage: python test_single_algorithm.py <algorithm_id>
"""

import os
import sys
import json
from pathlib import Path

# Set up QGIS environment - ADJUST THIS PATH TO YOUR QGIS INSTALLATION
qgis_path = r"C:\Program Files\QGIS 3.42.3\apps\qgis"
if not os.path.exists(qgis_path):
    # Try alternative path
    qgis_path = r"C:\Program Files\QGIS 3.38.3\apps\qgis"
    if not os.path.exists(qgis_path):
        qgis_path = r"C:\OSGeo4W\apps\qgis"
        if not os.path.exists(qgis_path):
            print(f"ERROR: QGIS not found at standard locations. Please update qgis_path in script.")
            sys.exit(1)

sys.path.insert(0, os.path.join(qgis_path, 'python'))
sys.path.insert(0, os.path.join(qgis_path, 'python', 'plugins'))

# Set QGIS prefix path
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qgis_path, 'qtplugins')
os.environ['PATH'] = os.path.join(qgis_path, 'bin') + ';' + os.environ['PATH']

from qgis.core import (
    QgsApplication,
    QgsProcessingFeedback,
    QgsProcessingContext,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsProcessingException
)

class ConsoleFeedback(QgsProcessingFeedback):
    """Simple feedback for console output."""
    
    def pushInfo(self, info):
        print(f"  INFO: {info}")
    
    def reportError(self, error, fatalError=False):
        print(f"  ERROR: {error}")
    
    def setProgressText(self, text):
        print(f"  PROGRESS: {text}")

def test_algorithm(algorithm_id):
    """Test a single algorithm and return result."""
    
    # Test file paths - UPDATE THESE TO YOUR ACTUAL PATHS
    test_files = {
        '2D': r'C:\GH\ras-commander-mappingbranch\examples\example_projects\BaldEagleCrkMulti2D\BaldEagleDamBrk.p01.hdf',
        '1D': r'C:\GH\ras-commander-mappingbranch\examples\example_projects\Balde Eagle Creek\BaldEagle.p01.hdf',
        'PIPE': r'C:\GH\ras-commander-mappingbranch\examples\example_projects\Davis\DavisStormSystem.p02.hdf'
    }
    
    # Check if test files exist
    missing_files = []
    for file_type, file_path in test_files.items():
        if not os.path.exists(file_path):
            missing_files.append(f"{file_type}: {file_path}")
    
    if missing_files:
        print("ERROR: Test HDF files not found. Please update paths in script:")
        for missing in missing_files:
            print(f"  - {missing}")
        print("\nHint: Look for HDF files in your HEC-RAS example projects folder")
        return {'algorithm': algorithm_id, 'status': 'failed', 'error': 'Test files not found', 'output': None}
    
    # Map algorithms to test files
    algorithm_test_map = {
        # 1D Algorithms
        'load_1d_cross_sections': '1D',
        'load_1d_river_centerlines': '1D',
        'load_1d_bank_lines': '1D',
        'load_1d_hydraulic_structures': '1D',
        'load_1d_xsec_results': '1D',
        
        # 2D Algorithms
        'load_2d_mesh_area_perimeters': '2D',
        'load_2d_mesh_cells': '2D',
        'load_2d_mesh_cell_faces': '2D',
        'load_2d_mesh_cell_points': '2D',
        'load_2d_breaklines': '2D',
        'load_2d_boundary_condition_lines': '2D',
        'load_2d_maximum_water_surface_points': '2D',
        'load_2d_maximum_iteration_count_points': '2D',
        'load_2d_minimum_water_surface_points': '2D',
        'load_2d_max_face_velocity_points': '2D',
        'load_2d_max_courant_points': '2D',
        'delineate_fluvial_pluvial_boundary': '2D',
        
        # Pipe Network
        'load_pipe_conduits': 'PIPE',
        'load_pipe_nodes': 'PIPE',
        
        # Metadata
        'load_plan_parameters': '2D',
        'load_runtime_statistics': '2D',
        'load_volume_accounting': '2D',
        
        # Analysis
        'analyze_benefit_areas': '2D',
        'load_2d_mesh_results': '2D',
    }
    
    print(f"\nTesting algorithm: {algorithm_id}")
    print("="*60)
    
    # Initialize QGIS
    QgsApplication.setPrefixPath(qgis_path, True)
    qgs = QgsApplication([], False)
    qgs.initQgis()
    
    result = {
        'algorithm': algorithm_id,
        'status': 'unknown',
        'error': None,
        'output': None
    }
    
    try:
        # Import processing after QGIS is initialized
        from qgis.analysis import QgsNativeAlgorithms
        import processing
        
        # Initialize processing
        QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
        
        # Load RAS Commander plugin - first try the development path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        
        # Add the project root to Python path so we can import ras_commander_qgis
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # Also add parent of project root for ras_commander imports
        parent_dir = os.path.dirname(project_root)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        # Import and initialize the plugin
        from ras_commander_qgis.processing.provider import RASCommanderProvider
        provider = RASCommanderProvider()
        QgsApplication.processingRegistry().addProvider(provider)
        
        # Get algorithm
        alg = QgsApplication.processingRegistry().algorithmById(f'ras_commander:{algorithm_id}')
        if not alg:
            result['status'] = 'not_found'
            result['error'] = 'Algorithm not found in registry'
            return result
        
        # Prepare parameters
        context = QgsProcessingContext()
        feedback = ConsoleFeedback()
        params = {}
        
        # Get test file
        file_key = algorithm_test_map.get(algorithm_id, '2D')
        test_file = test_files[file_key]
        
        # Special handling for different algorithms
        if algorithm_id == 'analyze_benefit_areas':
            params['EXISTING_HDF'] = test_file
            params['PROPOSED_HDF'] = test_file
            params['MIN_DELTA'] = 0.1
            params['OVERRIDE_CRS'] = QgsCoordinateReferenceSystem('EPSG:4326')
            params['OUTPUT_BENEFIT_AREAS'] = 'memory:'
            params['OUTPUT_RISE_AREAS'] = 'memory:'
            params['OUTPUT_EXISTING_POINTS'] = 'memory:'
            params['OUTPUT_PROPOSED_POINTS'] = 'memory:'
            params['OUTPUT_DIFFERENCE_POINTS'] = 'memory:'
        
        elif algorithm_id == 'delineate_fluvial_pluvial_boundary':
            params['INPUT_HDF'] = test_file
            params['TIME_THRESHOLD'] = 12.0
            params['MIN_SEGMENT_LENGTH'] = 150.0
            params['OVERRIDE_CRS'] = QgsCoordinateReferenceSystem('EPSG:4326')
            params['OUTPUT_LAYER'] = 'memory:'
        
        else:
            params['INPUT_HDF'] = test_file
            
            # Add CRS override for spatial algorithms
            param_names = [p.name() for p in alg.parameterDefinitions()]
            if 'OVERRIDE_CRS' in param_names:
                params['OVERRIDE_CRS'] = QgsCoordinateReferenceSystem('EPSG:4326')
            
            # Add output
            params['OUTPUT_LAYER'] = 'memory:'
            if algorithm_id == 'load_2d_mesh_results':
                import tempfile
                params['OUTPUT_MESH'] = os.path.join(tempfile.gettempdir(), 'test_mesh.nc')
        
        print(f"Input file: {test_file}")
        print("Running algorithm...")
        
        # Run algorithm
        output = alg.run(params, context, feedback)
        
        if output:
            result['status'] = 'success'
            result['output'] = str(output)
            print("✅ SUCCESS")
        else:
            result['status'] = 'failed'
            result['error'] = 'No output returned'
            print("❌ FAILED: No output")
            
    except QgsProcessingException as e:
        result['status'] = 'failed'
        result['error'] = f"Processing error: {str(e)}"
        print(f"❌ FAILED: {str(e)}")
        
    except Exception as e:
        result['status'] = 'crashed'
        result['error'] = f"{type(e).__name__}: {str(e)}"
        print(f"❌ CRASHED: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        qgs.exitQgis()
    
    return result

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_single_algorithm.py <algorithm_id>")
        sys.exit(1)
    
    print(f"Python executable: {sys.executable}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script location: {os.path.abspath(__file__)}")
    
    algorithm_id = sys.argv[1]
    result = test_algorithm(algorithm_id)
    
    # Write result to file for batch collection
    import json
    result_file = f"test_result_{algorithm_id}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    # Exit with appropriate code
    if result['status'] == 'success':
        sys.exit(0)
    elif result['status'] == 'crashed':
        sys.exit(2)
    else:
        sys.exit(1)