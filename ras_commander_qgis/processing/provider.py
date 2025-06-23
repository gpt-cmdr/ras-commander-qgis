# -*- coding: utf-8 -*-
"""
RAS Commander Processing Provider.
"""

import warnings
from qgis.core import QgsProcessingProvider, QgsMessageLog, Qgis
from PyQt5.QtGui import QIcon
import os


class RASCommanderProvider(QgsProcessingProvider):
    """Processing provider for RAS Commander algorithms."""
    
    def __init__(self):
        """Initialize the provider."""
        QgsProcessingProvider.__init__(self)

    def id(self):
        """Return the unique provider ID."""
        return 'ras_commander'

    def name(self):
        """Return the provider name."""
        return 'RAS Commander'

    def icon(self):
        """Return the provider icon."""
        plugin_dir = os.path.dirname(os.path.dirname(__file__))
        icon_path = os.path.join(plugin_dir, 'icon.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QgsProcessingProvider.icon(self)

    def longName(self):
        """Return the full provider name."""
        return 'RAS Commander - HEC-RAS Data Access'

    def loadAlgorithms(self):
        """Load all algorithms for this provider."""
        algorithms = []
        
        # Check if ras-commander is available at all
        try:
            # Temporarily suppress HDF5 version warnings during import
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="h5py is running against HDF5*")
                import ras_commander
                
            ras_commander_available = True
            QgsMessageLog.logMessage(
                f"ras-commander {ras_commander.__version__} loaded successfully",
                "RAS Commander",
                Qgis.Info
            )
            
        except ImportError as e:
            ras_commander_available = False
            QgsMessageLog.logMessage(
                f"ras-commander library not found: {e}. Please install it using: pip install ras-commander",
                "RAS Commander",
                Qgis.Critical
            )
        except Exception as e:
            ras_commander_available = False
            QgsMessageLog.logMessage(
                f"Error importing ras-commander: {e}. This may be due to HDF5 library compatibility issues.",
                "RAS Commander", 
                Qgis.Warning  # Changed from Critical to Warning
            )
        
        if not ras_commander_available:
            # Add a dummy algorithm that explains the issue
            from .alg_dummy_error import DummyErrorAlgorithm
            algorithms.append(DummyErrorAlgorithm())
            for alg in algorithms:
                self.addAlgorithm(alg)
            return
        
        # Try to import and add each algorithm, catching import errors
        algorithm_definitions = [
            # Project & Plan Metadata
            ('alg_load_plan_parameters', 'LoadPlanParametersAlgorithm'),
            ('alg_load_runtime_statistics', 'LoadRuntimeStatisticsAlgorithm'),
            ('alg_load_volume_accounting', 'LoadVolumeAccountingAlgorithm'),
            
            # 1D Geometry Layers
            ('alg_load_1d_cross_sections', 'Load1DCrossSectionsAlgorithm'),
            ('alg_load_1d_river_centerlines', 'Load1DRiverCenterlinesAlgorithm'),
            ('alg_load_1d_bank_lines', 'Load1DBankLinesAlgorithm'),
            ('alg_load_1d_hydraulic_structures', 'Load1DHydraulicStructuresAlgorithm'),
            
            # 1D Summary Results
            ('alg_load_1d_xsec_results', 'Load1DCrossSectionResultsAlgorithm'),
            
            # 2D Geometry Layers
            ('alg_load_2d_mesh_area_perimeters', 'Load2DMeshAreaPerimetersAlgorithm'),
            ('alg_load_2d_mesh_cells', 'Load2DMeshCellsAlgorithm'),
            ('alg_load_2d_mesh_cell_faces', 'Load2DMeshCellFacesAlgorithm'),
            ('alg_load_2d_mesh_cell_points', 'Load2DMeshCellPointsAlgorithm'),
            ('alg_load_2d_breaklines', 'Load2DBreaklinesAlgorithm'),
            ('alg_load_2d_bc_lines', 'Load2DBoundaryConditionLinesAlgorithm'),
            
            # Pipe Network Geometry
            ('alg_load_pipe_conduits', 'LoadPipeConduitsAlgorithm'),
            ('alg_load_pipe_nodes', 'LoadPipeNodesAlgorithm'),
            
            # 2D Summary Results
            ('alg_load_2d_max_wse_points', 'Load2DMaximumWaterSurfacePointsAlgorithm'),
            ('alg_load_2d_max_iter_points', 'Load2DMaximumIterationCountPointsAlgorithm'),
            ('alg_load_2d_min_wse_points', 'Load2DMinimumWaterSurfacePointsAlgorithm'),
            ('alg_load_2d_max_face_velocity_points', 'Load2DMaxFaceVelocityPointsAlgorithm'),
            ('alg_load_2d_max_courant_points', 'Load2DMaxCourantPointsAlgorithm'),
            
            # 2D Mesh Results
            ('alg_load_2d_mesh_results', 'Load2DMeshResultsAlgorithm'),
            
            # Analysis Algorithms
            ('alg_delineate_2d_fluvial_pluvial', 'Delineate2DFluvialPluvialBoundaryAlgorithm'),
            ('alg_analyze_benefit_areas', 'AnalyzeBenefitAreasAlgorithm'),
        ]
        
        for module_name, class_name in algorithm_definitions:
            try:
                # Import from the processing package (parent of provider)
                from importlib import import_module
                full_module_name = f'ras_commander_qgis.processing.{module_name}'
                module = import_module(full_module_name)
                algorithm_class = getattr(module, class_name)
                algorithms.append(algorithm_class())
            except Exception as e:
                # Log the error but continue loading other algorithms
                QgsMessageLog.logMessage(
                    f"Failed to load algorithm {class_name}: {e}",
                    "RAS Commander",
                    Qgis.Warning
                )
        
        if algorithms:
            QgsMessageLog.logMessage(
                f"Successfully loaded {len(algorithms)} algorithms",
                "RAS Commander",
                Qgis.Info
            )
        else:
            QgsMessageLog.logMessage(
                "No algorithms could be loaded. Please check the installation.",
                "RAS Commander",
                Qgis.Warning
            )
            # Add a dummy algorithm that explains the issue
            from .alg_dummy_error import DummyErrorAlgorithm
            algorithms.append(DummyErrorAlgorithm())
        
        for alg in algorithms:
            self.addAlgorithm(alg)