# ras_commander_qgis/processing/alg_load_runtime_statistics.py
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
    QgsField,
    QgsFeature,
    QgsWkbTypes,
    QgsFeatureSink,
    QgsProcessingUtils)
from PyQt5.QtCore import QMetaType

class LoadRuntimeStatisticsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads runtime statistics from a HEC-RAS results HDF file.
    
    This tool extracts simulation runtime data and performance statistics,
    and loads them as an attribute table in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return LoadRuntimeStatisticsAlgorithm()

    def name(self):
        return 'load_runtime_statistics'

    def displayName(self):
        return 'Load Runtime Statistics'

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
                    feedback.pushInfo(f"Runtime Statistics layer moved to 'Benefit Area Analysis' group")
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
                'Runtime Statistics',
                QgsProcessing.TypeVector # Generic type for table output
            )
        )

    def _pandas_dtype_to_qgs_field(self, col_name: str, dtype) -> QgsField:
        """
        Convert pandas dtype to QgsField using modern QMetaType.
        
        Args:
            col_name: The name of the column/field.
            dtype: The pandas dtype of the column.

        Returns:
            A configured QgsField instance using QMetaType.Type.
        """
        if pd.api.types.is_integer_dtype(dtype):
            return QgsField(col_name, QMetaType.Type.Int)
        elif pd.api.types.is_float_dtype(dtype):
            return QgsField(col_name, QMetaType.Type.Double)
        elif pd.api.types.is_bool_dtype(dtype):
            return QgsField(col_name, QMetaType.Type.Bool)
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            return QgsField(col_name, QMetaType.Type.QDateTime)
        else:
            # Default to string for object, category, etc.
            return QgsField(col_name, QMetaType.Type.QString)

    def _safe_value_convert(self, value):
        """
        Safely convert value for QGIS attribute setting.
        
        Returns:
            tuple: (is_valid: bool, converted_value: any)
        """
        # Handle None values
        if value is None:
            return False, None
        
        # Handle pandas/numpy NaN values
        try:
            if pd.isna(value):
                return False, None
        except (TypeError, ValueError):
            pass
        
        # Handle empty strings
        if isinstance(value, str) and value.strip() == "":
            return False, None
        
        # Handle numpy scalars
        if isinstance(value, (np.integer, np.floating)):
            try:
                if np.isnan(value):
                    return False, None
                return True, value.item()  # Convert to Python native type
            except (TypeError, ValueError):
                return True, value.item()
        
        # Handle datetime objects
        if hasattr(value, 'strftime'):
            return True, value.strftime('%Y-%m-%d %H:%M:%S')
        
        # Handle complex objects by converting to string
        if isinstance(value, (list, tuple, dict)):
            return True, str(value)
        
        # Default case
        return True, value

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)

        try:
            # Call ras-commander to get runtime data
            from ras_commander import HdfResultsPlan
            feedback.pushInfo(f"Loading runtime statistics from {hdf_path}...")
            
            df = HdfResultsPlan.get_runtime_data(hdf_path)
            
            if df is None or df.empty:
                feedback.pushInfo("No runtime statistics found in the HDF file. Creating empty layer.")
                fields = QgsFields()
                (sink, dest_id) = self.parameterAsSink(
                    parameters, self.OUTPUT_LAYER, context, fields, 
                    QgsWkbTypes.NoGeometry, context.project().crs()
                )
                return {self.OUTPUT_LAYER: dest_id}
            
        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed to load runtime statistics: {e}")

        # Define fields dynamically from the DataFrame
        fields = QgsFields()
        for col, dtype in df.dtypes.items():
            try:
                field = self._pandas_dtype_to_qgs_field(col, dtype)
                fields.append(field)
            except Exception as e:
                feedback.pushInfo(f"Warning: Could not create field for column '{col}': {e}")
                # Fallback to string field
                fields.append(QgsField(col, QMetaType.Type.QString))
        
        # Create the sink for table output
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.NoGeometry,
            context.project().crs()
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output table.")

        # Process each row in the DataFrame
        total_rows = len(df)
        successful_features = 0
        
        for i, (_, row) in enumerate(df.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            
            # Set attributes for each field
            for field in fields:
                col_name = field.name()
                if col_name in df.columns:
                    try:
                        # Get the raw value
                        raw_value = row[col_name]
                        
                        # Convert value safely
                        is_valid, converted_value = self._safe_value_convert(raw_value)
                        
                        if is_valid:
                            feature.setAttribute(col_name, converted_value)
                        else:
                            feature.setAttribute(col_name, None)
                            
                    except Exception as e:
                        feedback.pushInfo(f"Warning: Error processing column '{col_name}': {e}")
                        feature.setAttribute(col_name, None)
            
            # Add the feature to the sink
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

        feedback.pushInfo(f"Successfully processed {successful_features} out of {total_rows} runtime statistics entries.")
        
        return {self.OUTPUT_LAYER: dest_id}