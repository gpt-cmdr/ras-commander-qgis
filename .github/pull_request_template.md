## Summary

<!-- What does this PR do? 2-3 sentences. -->

## Type of Change

- [ ] New processing algorithm
- [ ] Bug fix
- [ ] QGIS UI improvement
- [ ] Documentation
- [ ] Refactor / code quality
- [ ] Other: ___

## LLM Self-Review

I (or my LLM agent) have reviewed this PR against the following criteria:

### Code Quality
- [ ] All public functions and classes have docstrings
- [ ] Logging uses `QgsMessageLog.logMessage()` with appropriate severity levels
- [ ] Error handling uses `QgsProcessingException` for user-facing errors
- [ ] File paths use `pathlib.Path`

### QGIS Patterns
- [ ] New algorithms inherit from `RASCommanderBaseAlgorithm`
- [ ] Algorithm follows `QgsProcessingAlgorithm` pattern (name, displayName, group, initAlgorithm, processAlgorithm)
- [ ] Field definitions use `QMetaType.Type` constructors (QGIS 3.38+)
- [ ] Output layers include proper CRS handling
- [ ] Algorithm registered in `provider.py`

### HEC-RAS
- [ ] Data extraction uses `ras-commander` library (not raw h5py)
- [ ] GeoDataFrame outputs converted to QGIS features correctly
- [ ] CRS preserved from source data when available

### N/A Items
<!-- List any checklist items that don't apply and why. -->

## Test Plan

<!-- How did you test this? Include QGIS version, sample HEC-RAS project, and steps. -->

- [ ] Tested in QGIS (version: ___)
- [ ] Algorithm appears in Processing Toolbox
- [ ] Runs successfully with sample HEC-RAS data
- [ ] Output layers have correct geometry and attributes

## LLM Attribution

<!-- Optional. If an LLM helped, note which one. -->

- [ ] LLM-assisted (tool: ___)
- [ ] Fully human-written
