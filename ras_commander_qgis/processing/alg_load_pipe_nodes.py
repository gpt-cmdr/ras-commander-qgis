# ras_commander_qgis/processing/alg_load_pipe_nodes.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
import h5py
import numpy as np
from shapely.geometry import Point

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
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsFeatureSink,
    QgsProcessingParameterCrs,
    QgsProcessingUtils)
from PyQt5.QtCore import QMetaType

class LoadPipeNodesAlgorithm(QgsProcessingAlgorithm):
    """
    Loads pipe nodes from a HEC-RAS geometry HDF file.
    
    This tool extracts pipe node geometry and attributes from the
    pipe network, and loads them as a point vector layer in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return LoadPipeNodesAlgorithm()

    def name(self):
        return 'load_pipe_nodes'

    def displayName(self):
        return 'Load Pipe Nodes'

    def group(self):
        return 'Pipe Network Geometry'

    def groupId(self):
        return 'ras_pipe_geometry'

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
                    feedback.pushInfo(f"Pipe Nodes layer moved to 'Benefit Area Analysis' group")
                else:
                    feedback.pushInfo("Could not move layer to group (layer created successfully)")
        
        return results

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_HDF,
                'Geometry or Plan HDF File (*.g*.hdf, *.p*.hdf)',
                behavior=QgsProcessingParameterFile.File,
                fileFilter='HEC-RAS HDF Files (*.g*.hdf *.p*.hdf *.hdf)'
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.OVERRIDE_CRS,
                'Override CRS (Optional)',
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                'Pipe Nodes',
                QgsProcessing.TypeVectorPoint
            )
        )

    def _get_pipe_nodes_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get pipe nodes without CRS conflicts.
        
        This bypasses the ras-commander GeoDataFrame creation to avoid pyproj conflicts.
        """
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                # Get projection information first
                from ras_commander import HdfBase
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Check if pipe nodes exist
                nodes_path = "Geometry/Pipe Nodes"
                if nodes_path not in hdf_file:
                    return None, None, []
                
                nodes_group = hdf_file[nodes_path]
                
                # Get attributes
                if 'Attributes' not in nodes_group:
                    return None, None, []
                
                attributes = nodes_group['Attributes'][()]
                attr_df = pd.DataFrame(attributes)
                
                # Decode byte string fields to UTF-8 strings
                string_columns = attr_df.select_dtypes([object]).columns
                for col in string_columns:
                    attr_df[col] = attr_df[col].apply(lambda x: x.decode('utf-8') if isinstance(x, bytes) else x)
                
                # Get points data
                if 'Points' not in nodes_group:
                    return None, None, []
                
                points = nodes_group['Points'][()]
                
                # Create Point geometries
                geometries = []
                for xy in points:
                    if len(xy) >= 2:
                        geometries.append(Point(xy[0], xy[1]))
                    else:
                        geometries.append(Point())  # Empty point
                
                # Create raw data structure
                raw_data = attr_df.to_dict('list')
                raw_data['geometry'] = geometries
                
                return proj_wkt, raw_data, [geom.wkt for geom in geometries]
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading pipe nodes directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Direct HDF Access to Bypass ras-commander CRS Issues ---
            feedback.pushInfo(f"Loading pipe nodes from {hdf_path}...")
            
            proj_wkt, raw_data, wkt_geometries = self._get_pipe_nodes_direct(hdf_path, feedback)
            
            if raw_data is None or len(wkt_geometries) == 0:
                raise QgsProcessingException("No pipe nodes found in the HDF file.")
            
            # Create raw DataFrame (no geometry column yet)
            raw_df = pd.DataFrame(raw_data)
            raw_df = raw_df.drop(columns=['geometry'])  # Remove geometry from DataFrame
            
            # Get CRS name for feedback (safely without using pyproj)
            crs_name = "Found in HEC-RAS project" if proj_wkt else "Unknown"
            
        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed during initial data load: {e}")

        # Check for CRS and apply override if necessary
        if proj_wkt:
            feedback.pushInfo(f"CRS found in HEC-RAS project: {crs_name}")
        elif override_crs and override_crs.isValid():
            proj_wkt = override_crs.toWkt()
            feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
        else:
            raise QgsProcessingException(
                "Coordinate Reference System (CRS) could not be determined. "
                "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                "or provide a valid Override CRS in the tool dialog."
            )

        try:
            # Reconstruct "Safe" GeoDataFrame within QGIS environment
            # CRITICAL: Do NOT pass crs to GeoDataFrame constructor to avoid pyproj conflicts
            feedback.pushInfo("Reconstructing geometry within QGIS environment...")
            geometry = [loads(wkt) for wkt in wkt_geometries]
            gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)  # No CRS passed here!
            
        except Exception as e:
            raise QgsProcessingException(f"Failed during geometry reconstruction: {e}")

        # Proceed with Feature Sink pattern using the safe GeoDataFrame
        fields = QgsFields()
        
        # Dynamically create fields based on available columns
        for col in gdf.columns:
            if col != 'geometry':
                # Map column types appropriately
                if gdf[col].dtype == 'object':
                    fields.append(QgsField(col, QMetaType.Type.QString))
                elif 'int' in str(gdf[col].dtype):
                    fields.append(QgsField(col, QMetaType.Type.Int))
                elif 'float' in str(gdf[col].dtype):
                    fields.append(QgsField(col, QMetaType.Type.Double))
                else:
                    fields.append(QgsField(col, QMetaType.Type.QString))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.Point,
            qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        total_features = len(gdf)
        feedback.pushInfo(f"Processing {total_features} pipe nodes...")
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            # Set attributes for all defined fields
            for field in fields:
                col_name = field.name()
                if col_name in row and pd.notna(row[col_name]):
                    feature.setAttribute(col_name, str(row[col_name]))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 500 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully processed {total_features} pipe nodes")
        return {self.OUTPUT_LAYER: dest_id}