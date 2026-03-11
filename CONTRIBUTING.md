# Contributing to RAS Commander QGIS Plugin

Thank you for your interest in contributing to the RAS Commander QGIS Plugin. This project provides QGIS Processing Provider algorithms for accessing HEC-RAS 6.x HDF data through the [ras-commander](https://github.com/gpt-cmdr/ras-commander) library.

Maintained by [CLB Engineering Corporation](https://clbengineering.com/). Licensed under the MIT License.

---

## Our Philosophy: Don't Ask Me, Ask a GPT!

This plugin was built with LLMs, and we welcome LLM-assisted contributions. Use whatever agent works for you: Claude Code, Codex, Aider, Cursor, Gemini, or anything else. We do not distinguish between human-written and LLM-assisted code. What matters is that the contribution is correct, well-tested, and follows the patterns in this repository.

The core idea: **LLM self-review before submission reduces maintainer burden and gets your PR merged faster.** Run your agent's review pass, check the boxes in the PR template, and submit with confidence.

Learn more about this approach: [LLM Forward Engineering](https://clbengineering.com/llm-forward)

---

## Quick Start

### 1. Fork and Clone

```bash
git clone https://github.com/<your-username>/ras-commander-qgis.git
cd ras-commander-qgis
```

### 2. Install in QGIS for Development

Copy (or symlink) `ras_commander_qgis/` into your QGIS plugins directory:
- **Windows**: `C:\Users\<Username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`

Install `ras-commander` into the QGIS Python environment (Windows: open OSGeo4W Shell **as Administrator**):

```bash
pip install ras-commander
```

### 3. Enable and Launch

Enable the plugin in QGIS (**Plugins > Manage and Install Plugins**), verify it appears in the Processing Toolbox, then point your LLM agent at the repository root and start working.

---

## The Self-Review Contract

Before submitting a pull request, run an LLM self-review pass on your changes. This is the single most impactful thing you can do to get your PR merged quickly. The PR template includes a checklist -- check every box honestly.

If your agent cannot confidently check a box, note what is uncertain. Partial self-review is better than none.

---

## LLM Self-Review Checklist

Have your agent verify each of these areas before you submit.

### Code Quality

- [ ] All public functions and classes have docstrings
- [ ] Logging uses `QgsMessageLog.logMessage()` with appropriate `Qgis.Info` / `Qgis.Warning` / `Qgis.Critical` levels
- [ ] Error handling uses `QgsProcessingException` for user-facing errors
- [ ] File paths use `pathlib.Path` (not string concatenation)
- [ ] No hardcoded paths or platform-specific assumptions

### QGIS Specifics

- [ ] New algorithms inherit from `RASCommanderBaseAlgorithm` (see `base_algorithm.py`)
- [ ] Algorithm class follows `QgsProcessingAlgorithm` pattern: `name()`, `displayName()`, `group()`, `groupId()`, `shortHelpString()`, `initAlgorithm()`, `processAlgorithm()`
- [ ] Parameter definitions use correct QGIS types (`QgsProcessingParameterFile`, `QgsProcessingParameterFeatureSink`, etc.)
- [ ] Output layers include proper CRS handling (set from source data or project CRS)
- [ ] Field definitions use `QMetaType.Type` constructors (not deprecated `QVariant` types) for QGIS 3.38+ compatibility
- [ ] Algorithm is registered in `provider.py` `loadAlgorithms()`
- [ ] Algorithm file follows naming convention: `alg_<action>_<subject>.py`

### HEC-RAS Specifics

- [ ] Data extraction uses `ras-commander` library classes (not raw `h5py`)
- [ ] HDF file inputs accept both geometry HDF (`*.g##.hdf`) and plan HDF (`*.p##.hdf`) as appropriate
- [ ] GeoDataFrame outputs are converted to QGIS features with correct geometry types
- [ ] Coordinate reference systems are preserved from source data when available

---

## What We Accept

- **New processing algorithms** that expose ras-commander functionality through QGIS
- **QGIS UI improvements** (better parameter handling, help strings, icons)
- **Bug fixes** with clear description of the problem and solution
- **Documentation improvements** (README, help strings, inline comments)
- **Test coverage** for existing or new algorithms
- **Performance improvements** with before/after evidence

## What We Don't Accept

- Changes that break QGIS Processing API compatibility (3.22+)
- New dependencies without strong justification and maintainer approval
- Algorithms that bypass `ras-commander` to access HDF files directly with `h5py`
- Changes that remove support for existing HEC-RAS file formats

---

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat(processing): Add channel capacity analysis algorithm
fix(geometry): Correct CRS handling for 1D cross-section output
docs: Update installation instructions for QGIS 3.42
refactor(base): Simplify HDF path validation in base algorithm
```

**Common prefixes**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

**Scope** (optional but encouraged): `processing`, `geometry`, `results`, `base`, `provider`

### LLM Attribution

If an LLM assisted with the contribution, include a co-author line:

```
feat(processing): Add breach results algorithm

Co-Authored-By: Claude <noreply@anthropic.com>
```

This is encouraged but not required. We value transparency about how code was produced.

---

## Adding a New Processing Algorithm

The most common contribution is a new algorithm. Follow these steps:

1. **Create** `ras_commander_qgis/processing/alg_<action>_<subject>.py` -- inherit from `RASCommanderBaseAlgorithm` and implement `name()`, `displayName()`, `group()`, `groupId()`, `shortHelpString()`, `initAlgorithm()`, `processAlgorithm()`. Use any existing algorithm file as a template.
2. **Register** the algorithm in `provider.py` in the `loadAlgorithms()` method.
3. **Test** in QGIS -- reload the plugin, verify the algorithm appears in the Processing Toolbox, runs without errors, and produces correct output layers.

---

## Community Standards

### Professional Conduct

This plugin is used in **safety-critical flood modeling workflows**. Contributions must prioritize correctness and reliability. Hydraulic engineers rely on this tool for floodplain mapping, dam breach analysis, and infrastructure design. Errors in data extraction can have real consequences.

### LLM Forward Principles

We follow the [LLM Forward](https://clbengineering.com/llm-forward) engineering approach:

1. **Professional responsibility first** -- public safety and engineering ethics are paramount
2. **LLMs accelerate, not replace** -- professional judgment remains with licensed engineers
3. **Multi-level verifiability** -- results can be checked in the QGIS GUI and the HEC-RAS GUI
4. **Open source** -- free tools that benefit the entire H&H community

### Code of Conduct

Be respectful and constructive. We are a small project with limited maintainer bandwidth. Clear, well-reviewed PRs are the best way to contribute.

---

## Getting Help

- **Plugin issues**: [Open an issue](https://github.com/gpt-cmdr/ras-commander-qgis/issues) on this repository
- **ras-commander library questions**: See the [ras-commander repository](https://github.com/gpt-cmdr/ras-commander)
- **QGIS Processing framework**: Consult the [QGIS Developer Cookbook](https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/)
- **HEC-RAS questions**: See the [HEC-RAS documentation](https://www.hec.usace.army.mil/software/hec-ras/)
- **LLM agent setup**: Point your agent at this repo and let it read `CLAUDE.md`, `README.md`, and `CONTRIBUTING.md`

---

**An open-source project of [CLB Engineering Corporation](https://clbengineering.com/).**
