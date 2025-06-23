"""
Diagnose QGIS and RAS Commander setup
"""
import os
import sys

print("="*60)
print("RAS Commander Test Diagnostics")
print("="*60)
print()

# 1. Check Python
print("1. Python Information:")
print(f"   Python executable: {sys.executable}")
print(f"   Python version: {sys.version}")
print(f"   Current directory: {os.getcwd()}")
print()

# 2. Check QGIS installation
print("2. Checking QGIS Installation:")
qgis_paths = [
    r"C:\Program Files\QGIS 3.42.3",
    r"C:\OSGeo4W",
    r"C:\OSGeo4W64"
]

qgis_found = False
for path in qgis_paths:
    if os.path.exists(path):
        print(f"   ✓ Found QGIS at: {path}")
        qgis_found = True
        # Check for apps/qgis subdirectory
        apps_qgis = os.path.join(path, "apps", "qgis")
        if os.path.exists(apps_qgis):
            print(f"     ✓ Found apps/qgis at: {apps_qgis}")
        else:
            print(f"     ✗ Missing apps/qgis subdirectory")
        break

if not qgis_found:
    print("   ✗ QGIS not found in standard locations!")
    print("   Please check your QGIS installation path")
print()

# 3. Check for test HDF files
print("3. Checking for test HDF files:")
test_paths = [
    r"C:\GH\ras-commander-mappingbranch\examples",
    r"C:\Users\Public\Documents\HEC Data\HEC-RAS\6.5\Example Data",
    r"C:\Users\Public\Documents\HEC Data\HEC-RAS\6.4.1\Example Data",
    r"C:\Users\Public\Documents\HEC Data\HEC-RAS\6.3.1\Example Data",
]

hdf_found = False
for path in test_paths:
    if os.path.exists(path):
        print(f"   ✓ Found directory: {path}")
        # Look for HDF files
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.hdf'):
                    print(f"     - HDF file: {os.path.join(root, file)}")
                    hdf_found = True
                    if hdf_found:
                        break
            if hdf_found:
                break
        if hdf_found:
            break

if not hdf_found:
    print("   ✗ No HDF test files found!")
    print("   Please update test_single_algorithm.py with paths to your HDF files")
print()

# 4. Check plugin location
print("4. Checking RAS Commander plugin:")
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
plugin_path = os.path.join(project_root, "ras_commander_qgis")

if os.path.exists(plugin_path):
    print(f"   ✓ Found plugin at: {plugin_path}")
    # Check for key files
    key_files = ["__init__.py", "plugin_main.py", "processing/provider.py"]
    for key_file in key_files:
        full_path = os.path.join(plugin_path, key_file)
        if os.path.exists(full_path):
            print(f"     ✓ {key_file}")
        else:
            print(f"     ✗ Missing: {key_file}")
else:
    print(f"   ✗ Plugin not found at: {plugin_path}")

print()
print("="*60)
print("Next steps:")
print("1. Update QGIS path in test_single_algorithm.py if needed")
print("2. Update HDF file paths in test_single_algorithm.py")
print("3. Make sure you're running from Windows PowerShell (not WSL)")
print("="*60)