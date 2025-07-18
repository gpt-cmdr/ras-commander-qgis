# RAS Commander QGIS Plugin

A QGIS Processing Provider for accessing HEC-RAS model data through the `ras-commander` library.

<div align="center">
  <img src="Images/ras-commander-qgis-logo.svg" alt="RAS Commander QGIS Plugins" width="600">

## Overview

The RAS Commander QGIS Plugin provides hydraulic modelers and GIS analysts with a seamless interface within QGIS for accessing, analyzing, and visualizing HEC-RAS model data. The plugin leverages the existing `ras-commander` Python library as its core engine and implements a modern QGIS Processing Provider architecture.

## Features

### Project & Plan Metadata
- Load Project Summary Tables (plan entries, geometry entries, unsteady entries, boundary conditions)
- Load Plan Parameters
- Load Runtime Statistics  
- Load Volume Accounting

### 1D Geometry Layers
- Load 1D Cross-Sections
- Load 1D River Centerlines
- Load 1D Bank Lines
- Load 1D Hydraulic Structures

### 2D Geometry Layers
- Load 2D Mesh Area Perimeters
- Load 2D Mesh Cells
- Load 2D Breaklines
- Load 2D Boundary Condition Lines

### Pipe Network Geometry
- Load Pipe Conduits
- Load Pipe Nodes

### Vector Results Layers
- Load Maximum Water Surface Points
- Load Maximum Iteration Count Points
- Load Minimum Water Surface Points

### Analysis Algorithms
- Delineate Fluvial-Pluvial Boundary

## Installation

### ⚠️ CRITICAL INSTALLATION WARNING ⚠️

**Windows users MUST run OSGeo4W Shell as Administrator for installation!**
- Right-click OSGeo4W Shell → Run as administrator
- Failure to do so will cause plugin crashes or break QGIS
- This is the #1 cause of installation problems

### Prerequisites
- **QGIS 3.22 or later** (3.38+ Recommended)
- **Administrator rights** (Windows users)

### Step 1: Install the `ras-commander` Library

⚠️ **CRITICAL: You MUST run OSGeo4W Shell as Administrator or the installation will fail and may break QGIS!**

#### Windows (OSGeo4W Shell) - REQUIRED ADMINISTRATOR RIGHTS

1. **Right-click** on the **OSGeo4W Shell** shortcut
2. Select **"Run as administrator"** 
3. **IMPORTANT**: If you don't run as administrator, the installation will fail with permission errors or crash the plugin when loading in QGIS

Once in the administrator OSGeo4W Shell, you have two options:

**Option A: Full Installation (Recommended if you have admin rights)**
```bash
pip install ras-commander
```

**Option B: No-dependencies Installation (If concerned about conflicts)**
```bash
pip install ras-commander --no-deps
```

**Why Administrator Rights are Required:**
- QGIS Python packages are installed in protected system directories
- Without admin rights, pip cannot properly install packages to QGIS's Python environment
- Running without admin rights often results in partial installations that crash when the plugin loads

#### Linux / Mac

1.  Identify the Python environment used by QGIS.
2.  Install `ras-commander` using `pip`, again with the `--no-deps` flag.

    ```bash
    pip install ras-commander --no-deps
    ```

#### **Recovery (If Something Goes Wrong)**

If you encounter issues, try these steps in order:

1. **If installed without administrator rights:**
   - Close QGIS completely
   - Open OSGeo4W Shell **as Administrator**
   - Reinstall ras-commander:
     ```bash
     pip uninstall ras-commander -y
     pip install ras-commander
     ```

2. **If QGIS libraries were accidentally upgraded:**
   ```bash
   # In Administrator OSGeo4W Shell
   pip install "numpy<2" --force-reinstall --no-deps
   pip install "h5py==3.7.0" --force-reinstall --no-deps
   ```

3. **If plugin crashes on load:**
   - Ensure OSGeo4W Shell was run as Administrator during installation
   - Check that ras-commander is properly installed: `pip show ras-commander`
   - Verify h5py compatibility in QGIS Python Console:
     ```python
     import h5py
     print(h5py.__version__)
     ```

#### Copy Plugin Files to QGIS Plugin Folder

Then copy the `ras_commander_qgis` folder to your QGIS plugins directory and enable it in QGIS.  
Typically located in C:\Users\(Username)\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins  
If you have no existing plugins, you may need to create the folder

### Installation Verification

After installation, you can verify the setup using the provided installation script:

```bash
# Run from within QGIS Python Console or OSGeo4W Shell
python install_script.py
```

This script will check:
- Python environment and version
- QGIS availability and version
- ras-commander installation and version
- h5py compatibility with QGIS environment

If you encounter h5py issues, the script provides a `diagnose_h5py_issue()` function to help troubleshoot.


## Usage

### Accessing the Tools

1. Open the **Processing Toolbox** (Processing > Toolbox)
2. Expand the **RAS Commander** provider
3. Browse the available algorithms organized by category
4. Double-click any algorithm to open its dialog

### Basic Workflow

1. **Load Project Metadata**: Start with "Load Project Summary Tables" to get an overview of your HEC-RAS project
2. **Load Geometry**: Use the geometry algorithms to load cross-sections, mesh cells, etc.
3. **Load Results**: Use the results algorithms to load water surface elevations and other computed values
4. **Analyze**: Use analysis tools like "Delineate Fluvial-Pluvial Boundary" for advanced analysis

### Input File Types

- **Project Folders**: For project summary data
- **Geometry HDF Files** (`*.g##.hdf`): For geometric data
- **Results HDF Files** (`*.p##.hdf`): For simulation results

## Development

### Project Structure

```
ras_commander_qgis/
├── __init__.py                  # Plugin entry point
├── plugin_main.py               # Main plugin class
├── metadata.txt                 # Plugin metadata
├── icon.png                     # Plugin icon
└── processing/
    ├── __init__.py
    ├── provider.py              # Processing provider
    ├── helpers.py               # Utility functions
    ├── alg_load_project_summary.py
    ├── alg_load_cross_sections.py
    └── ... (other algorithm files)
```

### Style Guide

- **Files**: `snake_case` (e.g., `alg_load_mesh_cells.py`)
- **Classes**: `PascalCase` (e.g., `LoadMeshCellsAlgorithm`)
- **Functions/Methods**: `snake_case` (e.g., `process_algorithm`)
- **Variables**: `snake_case` (e.g., `hdf_path`)
- **Constants**: `UPPER_CASE_WITH_UNDERSCORES`

### Adding New Algorithms

1. Create a new algorithm file in `processing/` following the naming convention
2. Implement the algorithm class inheriting from `QgsProcessingAlgorithm`
3. Add the import and algorithm instance to `provider.py`
4. Follow the existing patterns for error handling and user feedback

## Dependencies

- **QGIS**: 3.22+ (3.38+ recommended for best compatibility)
- **ras-commander**: Latest version
- **Python packages**: pandas, geopandas (typically included with QGIS)

### QGIS Version Compatibility

- **QGIS 3.22-3.37**: Fully supported
- **QGIS 3.38+**: Uses updated `QMetaType.Type` field constructors (recommended)
- **QGIS 3.42+**: Tested and verified

**Note**: This plugin has been updated to use the modern `QMetaType.Type` field constructors instead of the deprecated `QVariant` types, ensuring compatibility with QGIS 3.38+ and future QGIS 4.0. For technical details, see the [QGIS PyQGIS Developer Cookbook](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/vector.html).

## Contributing

1. Fork the repository
2. Create a feature branch
3. Follow the established coding style
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the same terms as the `ras-commander` library.

## Support

For issues related to:
- **Plugin functionality**: Open an issue in this repository
- **ras-commander library**: Refer to the ras-commander documentation
- **QGIS Processing framework**: Consult the QGIS documentation

## Acknowledgments

This plugin is built on top of the excellent `ras-commander` library and follows QGIS Processing framework best practices. 
