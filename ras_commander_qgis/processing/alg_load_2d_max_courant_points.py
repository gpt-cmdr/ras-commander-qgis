# ras_commander_qgis/processing/alg_load_2d_max_courant_points.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads

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
    QgsProcessingUtils
)
from PyQt5.QtCore import QMetaType


class Load2DMaxCourantPointsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads maximum Courant numbers from a HEC-RAS 2D results HDF file.
    
    This tool extracts the maximum Courant number at each 2D mesh face over 
    the simulation period, and loads them as a point layer at the face
    centers in QGIS. Useful for identifying areas of computational instability.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMaxCourantPointsAlgorithm()

    def name(self):
        return 'load_2d_max_courant_points'

    def displayName(self):
        return 'Load 2D Max Courant Number at Face Centers'

    def group(self):
        return '2D Summary Results'

    def groupId(self):
        return 'ras_2d_summary_results'

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        """Post-process to move the created layer to its designated group."""
        results = super().postProcessAlgorithm(context, feedback) or {}
        
        if self.OUTPUT_LAYER in results:
            layer_id = results[self.OUTPUT_LAYER]
            
            layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
            if layer:
                from .helpers import move_layer_to_group
                success = move_layer_to_group(layer.id(), self.group())
                if success:
                    feedback.pushInfo(f"{self.displayName()} layer moved to '{self.group()}' group")
        
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
            QgsProcessingParameterCrs(
                self.OVERRIDE_CRS,
                'Override CRS (Optional)',
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                '2D Results: Summary',
                QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Firewall Step 1: Call ras-commander ---
            from ras_commander import HdfResultsMesh
            feedback.pushInfo(f"Loading maximum Courant numbers from {hdf_path}...")
            initial_gdf = HdfResultsMesh.get_mesh_summary(hdf_path, var="Maximum Face Courant")
            
            if initial_gdf is None or initial_gdf.empty:
                raise QgsProcessingException("No maximum Courant number data found in the HDF file.")

            # --- Firewall Step 2: Deconstruct into primitives - CAPTURE CRS NAME IMMEDIATELY ---
            proj_wkt = initial_gdf.crs.to_wkt() if initial_gdf.crs else None
            crs_name = initial_gdf.crs.name if initial_gdf.crs else None  # ← CRITICAL: Capture NOW
            
            # Get WKT of original geometries (lines)
            wkt_geometries = initial_gdf.geometry.to_wkt()
            raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
            # ⚠️ NEVER reference initial_gdf after this point!

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
            # Reconstruct the "Safe" GeoDataFrame
            # CRITICAL: Do NOT pass crs to GeoDataFrame constructor to avoid pyproj conflicts
            feedback.pushInfo("Reconstructing geometry within QGIS environment...")
            
            # Load line geometries from WKT
            line_geometries = [loads(wkt) for wkt in wkt_geometries]
            
            # NOW convert lines to centroids (points) AFTER firewall
            point_geometries = [line.centroid for line in line_geometries]
            
            # Create GeoDataFrame with point geometries
            gdf = gpd.GeoDataFrame(raw_df, geometry=point_geometries)  # No CRS passed here!
            
        except Exception as e:
            raise QgsProcessingException(f"Failed during geometry reconstruction: {e}")

        # Create fields for the output layer
        fields = QgsFields()
        fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        fields.append(QgsField("face_id", QMetaType.Type.Int))
        fields.append(QgsField("max_courant", QMetaType.Type.Double))
        fields.append(QgsField("time_of_max", QMetaType.Type.QString))
        
        # Add any additional fields from the data
        for col in raw_df.columns:
            if col not in ['mesh_name', 'face_id', 'maximum_face_courant', 'maximum_face_courant_time']:
                fields.append(QgsField(col, QMetaType.Type.QString))

        # Create QGIS CRS object
        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        # Get the feature sink
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_LAYER, context, fields,
            QgsWkbTypes.Point, qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        # Process features
        total_features = len(gdf)
        courant_col = 'maximum_face_courant'
        time_col = 'maximum_face_courant_time'
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            # Set standard attributes
            if 'mesh_name' in row:
                feature.setAttribute("mesh_name", str(row.mesh_name))
            if 'face_id' in row:
                feature.setAttribute("face_id", int(row.face_id))
            if courant_col in row and pd.notna(row[courant_col]):
                feature.setAttribute("max_courant", float(row[courant_col]))
            if time_col in row and pd.notna(row[time_col]):
                feature.setAttribute("time_of_max", str(row[time_col]))
            
            # Set any additional attributes
            for col in raw_df.columns:
                if col not in ['mesh_name', 'face_id', courant_col, time_col] and col in row:
                    feature.setAttribute(col, str(row[col]))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            # Update progress every 2000 features
            if i % 2000 == 0:
                progress = int((i / total_features) * 100)
                feedback.setProgress(progress)
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully loaded {total_features} max Courant number points")
        return {self.OUTPUT_LAYER: dest_id} 