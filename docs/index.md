# RAS Commander QGIS

!!! note "A focused tool, not the full library"
    RAS Commander QGIS exposes a **limited subset** of capabilities inside the QGIS GUI. For the most powerful and complete way to automate HEC-RAS, use the [**ras-commander** library](https://rascommander.info/ras/) directly.

The **RAS Commander QGIS Plugin** is a QGIS Processing Provider for accessing HEC-RAS
model data through the [`ras-commander`](https://github.com/gpt-cmdr/ras-commander)
library. It gives hydraulic modelers and GIS analysts a seamless interface within QGIS
for accessing, analyzing, and visualizing HEC-RAS model data.

The plugin uses the existing `ras-commander` Python library as its core engine and
implements a modern QGIS Processing Provider architecture, so its tools appear alongside
native QGIS algorithms in the Processing Toolbox.

## What it does in QGIS

The plugin loads HEC-RAS project metadata, geometry, and results directly into QGIS as
tables and vector layers, and provides analysis algorithms. Capabilities include:

- **Project & plan metadata** — project summary tables, plan parameters, runtime
  statistics, and volume accounting.
- **1D geometry layers** — cross-sections, river centerlines, bank lines, and hydraulic
  structures.
- **2D geometry layers** — mesh area perimeters, mesh cells, breaklines, and boundary
  condition lines.
- **Pipe network geometry** — pipe conduits and pipe nodes.
- **Vector results layers** — maximum and minimum water surface points and maximum
  iteration count points.
- **Analysis algorithms** — delineate the fluvial-pluvial boundary.

See the [Features](features.md) page for the full list.

## Accessing the tools

1. Open the **Processing Toolbox** (Processing &rsaquo; Toolbox).
2. Expand the **RAS Commander** provider.
3. Browse the available algorithms, organized by category.
4. Double-click any algorithm to open its dialog.

## Basic workflow

1. **Load project metadata** — start with *Load Project Summary Tables* for an overview
   of your HEC-RAS project.
2. **Load geometry** — use the geometry algorithms to load cross-sections, mesh cells,
   and more.
3. **Load results** — use the results algorithms to load water surface elevations and
   other computed values.
4. **Analyze** — use analysis tools such as *Delineate Fluvial-Pluvial Boundary*.

## Input file types

- **Project folders** — for project summary data.
- **Geometry HDF files** (`*.g##.hdf`) — for geometric data.
- **Results HDF files** (`*.p##.hdf`) — for simulation results.

---

An open-source project of [CLB Engineering Corporation](https://clbengineering.com/),
creators of the `ras-commander` library, built using the
[LLM Forward](https://clbengineering.com/llm-forward) engineering approach.
