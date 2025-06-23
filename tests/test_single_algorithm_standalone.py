# test_single_algorithm_standalone.py
# -*- coding: utf-8 -*-
"""
Standalone test script that sets up QGIS environment properly.
Usage: python test_single_algorithm_standalone.py <algorithm_id>
"""

import os
import sys
import subprocess

def setup_qgis_environment():
    """Set up QGIS environment variables."""
    
    # Find QGIS installation
    qgis_paths = [
        r"C:\Program Files\QGIS 3.42.3",
        r"C:\Program Files\QGIS 3.38.3",
        r"C:\OSGeo4W64",
        r"C:\OSGeo4W"
    ]
    
    qgis_root = None
    for path in qgis_paths:
        if os.path.exists(path):
            qgis_root = path
            break
    
    if not qgis_root:
        print("ERROR: Could not find QGIS installation!")
        sys.exit(1)
    
    print(f"Found QGIS at: {qgis_root}")
    
    # Set environment variables
    os.environ['OSGEO4W_ROOT'] = qgis_root
    os.environ['QGIS_PREFIX_PATH'] = os.path.join(qgis_root, 'apps', 'qgis')
    
    # Add to PATH
    os.environ['PATH'] = ';'.join([
        os.path.join(qgis_root, 'bin'),
        os.path.join(qgis_root, 'apps', 'qgis', 'bin'),
        os.environ.get('PATH', '')
    ])
    
    # Set Python paths
    python_home = os.path.join(qgis_root, 'apps', 'Python312')
    if not os.path.exists(python_home):
        python_home = os.path.join(qgis_root, 'apps', 'Python39')
    
    os.environ['PYTHONHOME'] = python_home
    os.environ['PYTHONPATH'] = ';'.join([
        os.path.join(qgis_root, 'apps', 'qgis', 'python'),
        os.path.join(qgis_root, 'apps', 'qgis', 'python', 'plugins'),
        os.path.join(python_home, 'lib', 'site-packages'),
        os.environ.get('PYTHONPATH', '')
    ])
    
    # Set Qt plugin path
    os.environ['QT_PLUGIN_PATH'] = ';'.join([
        os.path.join(qgis_root, 'apps', 'qgis', 'qtplugins'),
        os.path.join(qgis_root, 'apps', 'qt5', 'plugins')
    ])
    
    # Add Python to sys.path
    sys.path.insert(0, os.path.join(qgis_root, 'apps', 'qgis', 'python'))
    sys.path.insert(0, os.path.join(qgis_root, 'apps', 'qgis', 'python', 'plugins'))

# Set up environment before importing QGIS
setup_qgis_environment()

# Now import QGIS
try:
    from qgis.core import (
        QgsApplication,
        QgsProcessingFeedback,
        QgsProcessingContext,
        QgsProject,
        QgsCoordinateReferenceSystem,
        QgsProcessingException
    )
    print("✓ Successfully imported QGIS modules")
except ImportError as e:
    print(f"✗ Failed to import QGIS modules: {e}")
    sys.exit(1)

# Import the rest of the test code
from test_single_algorithm import ConsoleFeedback, test_algorithm

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_single_algorithm_standalone.py <algorithm_id>")
        sys.exit(1)
    
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