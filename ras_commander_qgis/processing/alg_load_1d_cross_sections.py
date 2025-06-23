# ras_commander_qgis/processing/alg_load_cross_sections.py
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
    QgsProcessingParameterCrs
)
from PyQt5.QtCore import QMetaType
from .helpers import convert_complex_columns_to_string

class Load1DCrossSectionsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 1D cross-section cut lines from a HEC-RAS geometry HDF file.
    
    This tool extracts the geometry and attributes for all 1D cross-sections,
    including station-elevation data, Manning's n values, and hydraulic
    parameters, and loads them as a line vector layer in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load1DCrossSectionsAlgorithm()

    def name(self):
        return 'load_1d_cross_sections'

    def displayName(self):
        return 'Load 1D Cross-Sections'

    def group(self):
        return '1D Geometry Layers'

    def groupId(self):
        return 'ras_1d_geometry'

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
                'Cross-Sections',
                QgsProcessing.TypeVectorLine
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Firewall Step 1: Call ras-commander to get the initial GeoDataFrame ---
            from ras_commander import HdfXsec
            feedback.pushInfo(f"Loading cross-sections from {hdf_path}...")
            
            initial_gdf = HdfXsec.get_cross_sections(hdf_path)
            
            if initial_gdf is None or initial_gdf.empty:
                raise QgsProcessingException("No cross-sections found in the specified HDF file.")

            # --- Firewall Step 2: Deconstruct the GeoDataFrame into primitive types ---
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
            raise QgsProcessingException(f"Failed to load cross-section data: {e}")

        # --- Firewall Step 3: Reconstruct a "safe" GeoDataFrame within the QGIS environment ---
        # CRITICAL: Do NOT pass crs to GeoDataFrame constructor to avoid pyproj conflicts
        try:
            feedback.pushInfo("Reconstructing geometry within QGIS environment...")
            geometry = [loads(wkt) for wkt in wkt_geometries]
            gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)  # No CRS passed here!
        except Exception as e:
            raise QgsProcessingException(f"Failed during geometry reconstruction: {e}")

        # Convert columns with complex objects (lists, dicts) to strings for QGIS compatibility
        complex_cols = ['station_elevation', 'mannings_n', 'ineffective_blocks']
        gdf = convert_complex_columns_to_string(gdf, complex_cols)

        # --- Firewall Step 4: Proceed with the Feature Sink pattern using the safe GeoDataFrame ---
        
        # Define fields for the output layer
        fields = QgsFields()
        fields.append(QgsField("River", QMetaType.Type.QString))
        fields.append(QgsField("Reach", QMetaType.Type.QString))
        fields.append(QgsField("RS", QMetaType.Type.QString))
        fields.append(QgsField("Left Bank", QMetaType.Type.Double))
        fields.append(QgsField("Right Bank", QMetaType.Type.Double))
        fields.append(QgsField("station_elevation", QMetaType.Type.QString, 'Station-Elevation Profile'))
        fields.append(QgsField("mannings_n", QMetaType.Type.QString, "Manning's n Profile"))
        fields.append(QgsField("ineffective_blocks", QMetaType.Type.QString, "Ineffective Flow Areas"))

        # Create a QGIS CRS object from the determined WKT string
        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.LineString,
            qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        # Add features to the sink
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