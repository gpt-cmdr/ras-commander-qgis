# Features

The plugin's tools are exposed as QGIS Processing algorithms under the **RAS Commander**
provider in the Processing Toolbox, organized by category.

## Project & plan metadata

- **Load Project Summary Tables** — plan entries, geometry entries, unsteady entries, and
  boundary conditions.
- **Load Plan Parameters**
- **Load Runtime Statistics**
- **Load Volume Accounting**

## 1D geometry layers

- **Load 1D Cross-Sections**
- **Load 1D River Centerlines**
- **Load 1D Bank Lines**
- **Load 1D Hydraulic Structures**

## 2D geometry layers

- **Load 2D Mesh Area Perimeters**
- **Load 2D Mesh Cells**
- **Load 2D Breaklines**
- **Load 2D Boundary Condition Lines**

## Pipe network geometry

- **Load Pipe Conduits**
- **Load Pipe Nodes**

## Vector results layers

- **Load Maximum Water Surface Points**
- **Load Maximum Iteration Count Points**
- **Load Minimum Water Surface Points**

## Analysis algorithms

- **Delineate Fluvial-Pluvial Boundary**

## Input file types

These algorithms accept the following inputs:

- **Project folders** — for project summary data.
- **Geometry HDF files** (`*.g##.hdf`) — for geometric data.
- **Results HDF files** (`*.p##.hdf`) — for simulation results.
