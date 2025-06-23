# ras_commander_qgis/processing/base_algorithm.py
# -*- coding: utf-8 -*-
"""
Base algorithm class with standardized dependency checking, error handling,
and a structured workflow for RAS Commander algorithms.
"""

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSink,
    QgsProcessing,
    QgsProcessingException,
    QgsFields,
    QgsWkbTypes
)

class RASCommanderBaseAlgorithm(QgsProcessingAlgorithm):
    """
    A base class for algorithms that load data from HEC-RAS HDF files.

    This class provides a standardized structure:
    1. Checks for ras-commander dependency.
    2. Defines a standard HDF file input and a feature sink output.
    3. Implements a processAlgorithm method that calls a subclass-specific
       method to fetch data and then handles the feature creation.
    """
    
    # --- Constants for parameters ---
    INPUT_HDF = 'INPUT_HDF'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def __init__(self):
        """Initialize the base algorithm."""
        super().__init__()
        self._ras_commander_available = None

    def checkRasCommanderAvailable(self):
        """Check if the ras-commander library is available."""
        if self._ras_commander_available is None:
            try:
                import ras_commander
                self._ras_commander_available = True
            except ImportError:
                self._ras_commander_available = False
        return self._ras_commander_available

    def get_input_hdf_path(self, parameters, context):
        """Helper to get the HDF path from parameters."""
        return self.parameterAsFile(parameters, self.INPUT_HDF, context)

    # --- Methods for subclasses to override ---

    def get_layer_name(self) -> str:
        """Subclasses must return the descriptive name for the output layer."""
        raise NotImplementedError

    def get_ras_commander_func(self):
        """Subclasses must return the ras-commander function to call."""
        raise NotImplementedError

    def get_output_geometry_type(self):
        """Subclasses must return the QgsProcessing.TypeVector... for the output."""
        raise NotImplementedError

    def get_output_wkb_type(self):
        """Subclasses must return the QgsWkbTypes.Type for the sink."""
        raise NotImplementedError

    def define_output_fields(self) -> QgsFields:
        """Subclasses must define the QgsFields for the output layer."""
        raise NotImplementedError
    
    def get_extra_parameters(self) -> list:
        """Subclasses can add extra parameters if needed."""
        return []
    
    def processAlgorithm(self, parameters, context, feedback):
        """Main processing logic for all subclasses."""
        if not self.checkRasCommanderAvailable():
            raise QgsProcessingException(
                "The ras-commander library is not available. Please see the plugin's "
                "README for installation instructions."
            )

        # Get HDF path and other parameters
        hdf_path = self.get_input_hdf_path(parameters, context)
        
        # --- 1. Fetch data using subclass-specific function ---
        try:
            ras_func = self.get_ras_commander_func()
            feedback.pushInfo(f"Loading data from {hdf_path}...")
            # This part will be specific to each algorithm's needs
            # For simplicity, we'll assume a standard call signature here
            # More complex logic can be handled by overriding processAlgorithm
            gdf = ras_func(hdf_path)
        except Exception as e:
            raise QgsProcessingException(f"Failed to load data from HDF: {e}")

        if gdf is None or gdf.empty:
            raise QgsProcessingException(f"No data found for '{self.get_layer_name()}' in the HDF file.")

        feedback.pushInfo(f"Found {len(gdf)} features. Writing to output layer...")

        # --- 2. Define fields and get the feature sink ---
        fields = self.define_output_fields()
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            self.get_output_wkb_type(),
            gdf.crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        # --- 3. Loop and add features to the sink ---
        total_features = len(gdf)
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break

            feature = QgsFeature()
            feature.setFields(fields)
            
            # Set geometry and attributes
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            for field in fields:
                col_name = field.name()
                if col_name in row:
                    feature.setAttribute(col_name, row[col_name])

            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            if i % 2000 == 0:
                feedback.setProgress(int((i / total_features) * 100))

        if feedback.isCanceled():
            return {}

        return {self.OUTPUT_LAYER: dest_id}

    def initAlgorithm(self, config=None):
        """Initialize parameters for the algorithm."""
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_HDF,
                'Geometry or Plan HDF File (*.g*.hdf, *.p*.hdf)',
                behavior=QgsProcessingParameterFile.File,
                fileFilter='HEC-RAS HDF Files (*.g*.hdf *.p*.hdf *.hdf)'
            )
        )
        
        # Add any extra parameters defined by the subclass
        for param in self.get_extra_parameters():
            self.addParameter(param)
            
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                self.get_layer_name(),
                self.get_output_geometry_type()
            )
        )