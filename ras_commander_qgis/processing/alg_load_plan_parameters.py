# ras_commander_qgis/processing/alg_load_plan_parameters.py
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingContext,
    QgsProcessingParameterFeatureSink,
    QgsProcessing,
    QgsProcessingException,
    QgsFields,
    QgsFeature,
    QgsWkbTypes,
    QgsFeatureSink,
    QgsProcessingUtils)
from .helpers import pandas_dtype_to_qgs_field

class LoadPlanParametersAlgorithm(QgsProcessingAlgorithm):
    """
    Loads plan parameters from a HEC-RAS results HDF file.
    
    This tool extracts plan configuration parameters and settings,
    and loads them as an attribute table in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return LoadPlanParametersAlgorithm()

    def name(self):
        return 'load_plan_parameters'

    def displayName(self):
        return 'Load Plan Parameters'

    def group(self):
        return 'Project & Plan Metadata'

    def groupId(self):
        return 'ras_project_metadata'

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        """Post-process to move the created layer to the Benefit Area Analysis group."""
        results = super().postProcessAlgorithm(context, feedback) or {}
        
        # Move the output layer to the Benefit Area Analysis group
        if self.OUTPUT_LAYER in results:
            layer_id = results[self.OUTPUT_LAYER]
            
            # For sinks, we need to get the actual layer
            layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
            if layer:
                from .helpers import move_layer_to_benefit_area_group
                success = move_layer_to_benefit_area_group(layer.id())
                if success:
                    feedback.pushInfo(f"Plan Parameters layer moved to 'Benefit Area Analysis' group")
                else:
                    feedback.pushInfo("Could not move layer to group (layer created successfully)")
        
        return results

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_HDF,
                'Plan Results HDF File (*.p##.hdf)',
                behavior=QgsProcessingParameterFile.File,
                fileFilter='HEC-RAS HDF Results Files (*.p*.hdf *.hdf)'
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                'Plan Parameters',
                QgsProcessing.TypeVector # Generic type for table output
            )
        )

    def _safe_value_check_and_convert(self, value):
        """
        Safely check if a value is valid (not None/NaN/empty) and convert it for QGIS.
        
        Returns:
            tuple: (is_valid: bool, converted_value: any)
        """
        # Handle None values
        if value is None:
            return False, None
        
        # Handle numpy/pandas NaN values - use try/catch to avoid array issues
        try:
            if pd.isna(value):
                return False, None
        except (TypeError, ValueError):
            # pd.isna() might fail on complex types or arrays, continue processing
            pass
        
        # Handle arrays/lists - convert to string if they contain data
        if isinstance(value, (list, tuple, np.ndarray)):
            if len(value) == 0:
                return False, None
            # Convert to string representation
            return True, str(value)
        
        # Handle dictionaries
        if isinstance(value, dict):
            if len(value) == 0:
                return False, None
            return True, str(value)
        
        # Handle empty strings - THIS IS THE KEY FIX
        if isinstance(value, str):
            if value.strip() == "":
                return False, None  # Convert empty strings to None
            return True, value.strip()  # Return cleaned string
        
        # Handle numpy scalars
        if isinstance(value, (np.integer, np.floating)):
            try:
                if np.isnan(value):
                    return False, None
            except (TypeError, ValueError):
                pass  # Some numpy types can't be checked with isnan
            return True, value.item()  # Convert to Python native type
        
        # Handle pandas scalars and arrays more carefully
        if hasattr(value, 'dtype'):
            try:
                # Try to convert to a simple Python type
                if hasattr(value, 'item'):
                    return True, value.item()
                elif hasattr(value, 'values'):
                    # This is likely a pandas Series/array, convert to string
                    return True, str(value)
            except (ValueError, TypeError):
                # If conversion fails, convert to string
                return True, str(value)
        
        # For other types, check if they evaluate to something meaningful
        try:
            if not value and value != 0 and value != False:  # Allow 0 and False as valid values
                return False, None
        except (ValueError, TypeError):
            # Some types can't be evaluated in boolean context, assume they're valid
            pass
        
        return True, value

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)

        try:
            from ras_commander import HdfPlan
            feedback.pushInfo(f"Loading plan parameters from {hdf_path}...")
            df = HdfPlan.get_plan_parameters(hdf_path)
        except Exception as e:
            raise QgsProcessingException(f"Failed to load plan parameters: {e}")

        if df is None or df.empty:
            feedback.pushInfo("No plan parameters found in the HDF file. Returning empty layer.")
            # Create an empty sink to return a valid but empty output
            fields = QgsFields()
            (sink, dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_LAYER, context, fields, QgsWkbTypes.NoGeometry, context.project().crs()
            )
            return {self.OUTPUT_LAYER: dest_id}

        # Define fields dynamically from the DataFrame using the improved helper
        fields = QgsFields()
        for col, dtype in df.dtypes.items():
            fields.append(pandas_dtype_to_qgs_field(col, dtype))
        
        # Get the sink for the table (non-spatial) output
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.NoGeometry, # Specify NoGeometry for a table
            context.project().crs() # CRS is not critical but required
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output table.")

        # Add features (rows) to the sink
        total_rows = len(df)
        successful_features = 0
        
        for i, (_, row) in enumerate(df.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            
            # Process each field/column using safer approach
            for field in fields:
                col_name = field.name()
                if col_name in df.columns:
                    try:
                        # Get the raw value - be careful about arrays/series
                        if hasattr(row, 'loc'):
                            raw_value = row.loc[col_name]
                        else:
                            raw_value = row[col_name]
                        
                        # Use the safe value checker
                        is_valid, converted_value = self._safe_value_check_and_convert(raw_value)
                        
                        if is_valid:
                            try:
                                feature.setAttribute(col_name, converted_value)
                            except Exception as e:
                                # If setting the attribute fails, log it and set to None
                                feedback.pushInfo(f"Warning: Could not set attribute '{col_name}' with value '{converted_value}': {e}")
                                feature.setAttribute(col_name, None)
                        else:
                            # Set to None for invalid/empty values
                            feature.setAttribute(col_name, None)
                            
                    except Exception as e:
                        feedback.pushInfo(f"Warning: Error processing column '{col_name}': {e}")
                        feature.setAttribute(col_name, None)
            
            # Try to add the feature
            try:
                sink.addFeature(feature, QgsFeatureSink.FastInsert)
                successful_features += 1
            except Exception as e:
                feedback.pushInfo(f"Warning: Could not add feature {i}: {e}")
            
            # Update progress
            if i % 10 == 0:
                feedback.setProgress(int((i / total_rows) * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully processed {successful_features} out of {total_rows} plan parameter entries.")
        
        return {self.OUTPUT_LAYER: dest_id}