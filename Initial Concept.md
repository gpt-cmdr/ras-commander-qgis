Below is a roadmap you can use as a reference “back-of-napkin” plan.  Nothing here is rigid — treat each step as a checkpoint that can be expanded or collapsed to fit your timeline.

---

## 0  Take Stock of What You Already Have

| What                                                                                                | Why it matters for integration                                                                                              |
| --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **RAS Commander functions**<br>✓ return `GeoDataFrame` objects                                      | ArcGIS and QGIS both understand vector layers; a GeoDataFrame is a nice lingua-franca starting point.                       |
| **Dependencies** (`h5py`, `numpy`, `pandas`, `geopandas`, `shapely`, `pyproj`, …)                   | ArcGIS Pro ships its own conda env; QGIS bundles its own copy of GDAL/PyQt. Version mismatches are the #1 install headache. |
| **Typical HEC-RAS artefacts you care about** (cross-section lines, water-surface profiles, rasters) | Listing these now dictates the *tools/algorithms* you expose later.                                                         |

---

## 1  Refactor / wrap RAS Commander for GIS callers

1. **Pure-Python façade**

   * Functions accept only basic types (file paths, layer names, options dict).
   * Always return one of: `GeoDataFrame`, `DataFrame`, `xarray`, or simple scalars.

2. **Lightweight CLI entry point (optional)**

   * `python -m ras_commander.cli extract-crosssections --hdf <file> --out <gpkg>`
   * Lets you test in isolation and gives power-users a headless route.

3. **Add “export helpers”**

   ```python
   def to_feature_class(gdf, out_fc, overwrite=True): …
   def to_qgis_layer(gdf, layer_name, crs="EPSG:4326"): …
   ```

   Keep GIS-specific glue *here* so your toolbox/plugin scripts stay tiny.

---

## 2  ESRI Toolbox (ArcGIS Pro)

### 2.1  Decide format

* **Python Toolbox (`.pyt`)** — easiest to version-control, one file, reads like a class.
* **Script Tools inside a `.tbx`** — if teammates expect the classic GUI-builder.

### 2.2  Workflow skeleton

```text
<YourToolbox>.pyt
└── class ExtractCrossSections(object):
    ├── def __init__(self):              # define parameter list
    ├── def getParameterInfo(self): …
    └── def execute(self, params, msgs):
            import ras_commander as rc
            gdf = rc.extract_crosssections(params[0].valueAsText)
            rc.to_feature_class(gdf, params[1].valueAsText)
```

### 2.3  Environment & packaging

* Clone the default *arcgispro-py3* conda env → `ras-commander-env`.
* `conda install geopandas shapely …` (or use `pip install ras_commander---whl`).
* Ship a `environment.yml` “one-click” installer and document the *Activate Env* step inside the toolbox metadata.

### 2.4  UX polish

* Parameter filters (file picker that only shows `*.hdf`).
* Validation → warn if CRS missing, etc.
* Optional: add a *Geoprocessing Model* that chains `ExtractCrossSections` → `GenerateRaster` → `Contour` so analysts can see “what good looks like”.

---

## 3  QGIS Plugin

### 3.1  Plugin type

* Use **Processing Provider** style so each RAS function appears as an algorithm in the *Processing Toolbox*.
* Scaffold with *Plugin Builder 3* (`pb_tool create ras_commander_qgis`).

### 3.2  Boilerplate outline

```
ras_commander_qgis/
├── processing/
│   ├── provider.py          # registers algorithms
│   └── alg_extract_xs.py    # one file per geo algorithm
├── gui/
│   └── dock_widget.py       # optional, nice for live preview
├── ras_commander_helpers.py
└── metadata.txt
```

Inside `alg_extract_xs.py`:

```python
from qgis.PyQt.QtCore import QVariant
from qgis.processing import QgsProcessingAlgorithm, QgsProcessingParameterFile…
from ras_commander_helpers import extract_xs, to_qgis_layer

class ExtractXSAlg(QgsProcessingAlgorithm):
    …
    def processAlgorithm(self, params, context, feedback):
        gdf = extract_xs(params['HDF'])
        layer = to_qgis_layer(gdf, 'XS', gdf.crs)
        return {'OUTPUT': layer.id()}
```

### 3.3  Distribution

* Zip the plugin, bump `version` in `metadata.txt`.
* Test on the *LTR* and latest QGIS builds (Windows & Linux).
* For optional binaries (e.g., PROJ / GDAL), rely on the QGIS-embedded stack; avoid bundling DLLs unless absolutely necessary.

---

## 4  Shared Concerns & Complexities

| Area                         | ArcGIS Pro                                                                  | QGIS                                                                           | Notes                                                                                                |
| ---------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| **Python versions**          | 3.9 (Pro 3.3) → locked to Esri’s conda build                                | 3.11 + bundled GDAL                                                            | Stick to lowest‐common-denominator syntax; pin `ras_commander` to compatible wheels.                 |
| **CRS handling**             | Esri’s WKT2, factory codes                                                  | EPSG strings                                                                   | Normalise with `pyproj.CRS.from_user_input`.                                                         |
| **GeoDataFrame → Layer**     | Must round-trip via FGDB or `arcpy.da` cursors; speed hit for large rasters | `QgsVectorLayer.fromWkb` directly consumes WKB; faster                         | For performance-critical pieces, allow direct `arcpy.Array`/`QgsGeometry` creation to skip disk I/O. |
| **Licensing**                | Toolbox code inherits ArcGIS EULA; 3rd-party libs need review               | Fully GPL; mixing GPL + proprietary code OK because you call ArcGIS externally | Keep RAS Commander MIT/BSD style to avoid clashes.                                                   |
| **Packaging**                | Users fear conda; provide “Toolbox + env YAML” bundle                       | Users expect “install from ZIP”                                                | Video / GIF walkthroughs help adoption more than docs alone.                                         |
| **Binary deps (GDAL, HDF5)** | Already in ArcGIS; but versions can lag → segfault risk                     | Already in QGIS; also version-pinned                                           | Test early with big-endian HDF-5 rasters to catch ABI mismatches.                                    |
| **UI/UX**                    | ArcGIS GP dialog auto-generated; limited but stable                         | Qt Designer gives full freedom                                                 | Weigh UI complexity vs. maintenance; default to *Processing* for both.                               |
| **Testing**                  | `pytest-arcgis` or launch Pro headless via `python -m arcgispro`            | CI can run `qgis_process` headless                                             | Focus integration tests on “does a layer show up with correct CRS and feature count”.                |

---

## 5  Getting from “Plan” to “First Working Demo” in Two Sprints

| Sprint | Goal                   | Deliverables                                                            |
| ------ | ---------------------- | ----------------------------------------------------------------------- |
| **1**  | Library + CLI stable   | *ras-commander v1.0* on PyPI, sample notebook, sample HDF               |
| **2**  | Toolbox & Plugin alpha | `RASCommander.pyt`, `ras_commander_qgis.zip`, readme with install steps |

---

### Quick sanity checklist before release

* [ ] Re-open a saved MXD/APRX and QGS project – layers still resolve?
* [ ] Install in a virgin VM → no manual `pip install` needed?
* [ ] CRS of output matches river model’s projection?
* [ ] Performance acceptable on a 500 MB HDF?
* [ ] User cancels mid-run → graceful cleanup (temp files, locks).
* [ ] Logo/icon sized ≤ 256 × 256, transparent PNG.

---

**Bottom line:**
The “hard” parts are **environment packaging** and **geometry hand-off** (GeoDataFrame → FeatureClass / QgsVectorLayer).  Keep those pain points isolated in helper utilities, and both the ArcGIS toolbox and the QGIS plugin shrink to thin wrappers that should survive API or UI churn for years.  Once that scaffolding is solid, adding new RAS Commander capabilities is just “drop-in a new Processing algorithm / Script Tool” work.
