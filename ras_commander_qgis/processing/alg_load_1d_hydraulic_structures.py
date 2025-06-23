# ras_commander_qgis/processing/alg_load_hydraulic_structures.py
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
    QgsProcessingUtils)
from PyQt5.QtCore import QMetaType

class Load1DHydraulicStructuresAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 1D hydraulic structures from a HEC-RAS geometry HDF file.
    
    This tool extracts hydraulic structure geometry and attributes including
    bridges, culverts, weirs, and other structures, and loads them as a
    vector layer in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load1DHydraulicStructuresAlgorithm()

    def name(self):
        return 'load_1d_hydraulic_structures'

    def displayName(self):
        return 'Load 1D Hydraulic Structures'

    def group(self):
        return '1D Geometry Layers'

    def groupId(self):
        return 'ras_1d_geometry'

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
                    feedback.pushInfo(f"Hydraulic Structures layer moved to 'Benefit Area Analysis' group")
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
                'Hydraulic Structures',
                QgsProcessing.TypeVectorAnyGeometry
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Firewall Step 1: Call ras-commander ---
            from ras_commander import HdfStruc
            feedback.pushInfo(f"Loading hydraulic structures from {hdf_path}...")
            
            initial_gdf = HdfStruc.get_structures(hdf_path)
            if initial_gdf is None or initial_gdf.empty:
                raise QgsProcessingException("No hydraulic structures found in the HDF file.")

            # --- Firewall Step 2: Deconstruct and Handle CRS ---
            proj_wkt = None
            if initial_gdf.crs:
                proj_wkt = initial_gdf.crs.to_wkt()
                feedback.pushInfo(f"CRS found in HEC-RAS project: {initial_gdf.crs.name}")
            elif override_crs and override_crs.isValid():
                proj_wkt = override_crs.toWkt()
                feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
            else:
                raise QgsProcessingException(
                    "Coordinate Reference System (CRS) could not be determined. "
                    "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                    "or provide a valid Override CRS in the tool dialog."
                )

            wkt_geometries = initial_gdf.geometry.to_wkt()
            raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))

        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed to load hydraulic structures: {e}")

        # --- Firewall Step 3: Reconstruct "Safe" GeoDataFrame ---
        # CRITICAL: Do NOT pass crs to GeoDataFrame constructor to avoid pyproj conflicts
        try:
            feedback.pushInfo("Reconstructing geometry within QGIS environment...")
            geometry = [loads(wkt) for wkt in wkt_geometries]
            gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)  # No CRS passed here!
        except Exception as e:
            raise QgsProcessingException(f"Failed during geometry reconstruction: {e}")

        # --- Firewall Step 4: Proceed with Feature Sink ---
        fields = QgsFields()
        fields.append(QgsField("River", QMetaType.Type.QString))
        fields.append(QgsField("Reach", QMetaType.Type.QString))
        fields.append(QgsField("RS", QMetaType.Type.QString))
        fields.append(QgsField("Type", QMetaType.Type.QString))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.LineString, # HdfStruc.get_structures returns LineStrings
            qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        total_features = len(gdf)
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
                    feature.setAttribute(col_name, row[col_name])
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 100 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        return {self.OUTPUT_LAYER: dest_id}