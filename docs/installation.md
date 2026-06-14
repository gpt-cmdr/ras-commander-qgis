# Installation

!!! danger "Critical installation warning"
    **Windows users MUST run the OSGeo4W Shell as Administrator for installation.**

    - Right-click the **OSGeo4W Shell** shortcut &rsaquo; **Run as administrator**.
    - Failure to do so will cause plugin crashes or break QGIS.
    - This is the #1 cause of installation problems.

## Prerequisites

- **QGIS 3.22 or later** (3.38+ recommended).
- **Administrator rights** (Windows users).

## Step 1: Install the `ras-commander` library

!!! warning
    You **MUST** run the OSGeo4W Shell as Administrator, or the installation will fail
    and may break QGIS.

### Windows (OSGeo4W Shell) — administrator rights required

1. **Right-click** the **OSGeo4W Shell** shortcut.
2. Select **Run as administrator**.
3. If you don't run as administrator, the installation will fail with permission errors
   or crash the plugin when loading in QGIS.

Once in the administrator OSGeo4W Shell, choose one of the following:

**Option A: Full installation (recommended if you have admin rights)**

```bash
pip install ras-commander
```

**Option B: No-dependencies installation (if concerned about conflicts)**

```bash
pip install ras-commander --no-deps
```

**Why administrator rights are required:**

- QGIS Python packages are installed in protected system directories.
- Without admin rights, pip cannot properly install packages into QGIS's Python environment.
- Running without admin rights often results in partial installations that crash when the
  plugin loads.

### Linux / Mac

1. Identify the Python environment used by QGIS.
2. Install `ras-commander` using `pip`, again with the `--no-deps` flag:

   ```bash
   pip install ras-commander --no-deps
   ```

## Step 2: Copy the plugin into the QGIS plugins folder

Copy the `ras_commander_qgis` folder into your QGIS plugins directory and enable it in
QGIS. The directory is typically located at:

```
C:\Users\(Username)\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
```

If you have no existing plugins, you may need to create the folder.

## Installation verification

After installation, verify the setup using the provided installation script:

```bash
# Run from within the QGIS Python Console or OSGeo4W Shell
python install_script.py
```

This script checks:

- Python environment and version.
- QGIS availability and version.
- `ras-commander` installation and version.
- h5py compatibility with the QGIS environment.

If you encounter h5py issues, the script provides a `diagnose_h5py_issue()` function to
help troubleshoot.

## Recovery (if something goes wrong)

If you encounter issues, try these steps in order:

1. **If installed without administrator rights:**
    - Close QGIS completely.
    - Open the OSGeo4W Shell **as Administrator**.
    - Reinstall `ras-commander`:

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

3. **If the plugin crashes on load:**
    - Ensure the OSGeo4W Shell was run as Administrator during installation.
    - Confirm `ras-commander` is installed: `pip show ras-commander`.
    - Verify h5py compatibility in the QGIS Python Console:

      ```python
      import h5py
      print(h5py.__version__)
      ```

## QGIS version compatibility

- **QGIS 3.22–3.37** — fully supported.
- **QGIS 3.38+** — uses updated `QMetaType.Type` field constructors (recommended).
- **QGIS 3.42+** — tested and verified.

The plugin uses the modern `QMetaType.Type` field constructors instead of the deprecated
`QVariant` types, ensuring compatibility with QGIS 3.38+ and future QGIS 4.0.

## Dependencies

- **QGIS** — 3.22+ (3.38+ recommended for best compatibility).
- **ras-commander** — latest version.
- **Python packages** — pandas, geopandas (typically included with QGIS).
