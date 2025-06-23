# ras_commander_qgis/processing/alg_load_2d_max_iter_points.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point
import h5py
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
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsFeatureSink,
    QgsProcessingParameterCrs,
    QgsProcessingUtils)
from PyQt5.QtCore import QMetaType

class Load2DMaximumIterationCountPointsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads maximum iteration count points from a HEC-RAS 2D results HDF file.
    
    This tool extracts the maximum iteration count at each 2D mesh cell
    center over the entire simulation period, and loads them as a point
    vector layer. Useful for identifying computational difficulty areas.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMaximumIterationCountPointsAlgorithm()

    def name(self):
        return 'load_2d_maximum_iteration_count_points'

    def displayName(self):
        return 'Load 2D Max Iterations at Cell Centers'

    def group(self):
        return '2D Summary Results'

    def groupId(self):
        return 'ras_2d_summary_results'

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        results = super().postProcessAlgorithm(context, feedback) or {}
        if self.OUTPUT_LAYER in results:
            layer_id = results[self.OUTPUT_LAYER]
            layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
            if layer:
                from .helpers import move_layer_to_group
                success = move_layer_to_group(layer.id(), self.group())
                if success:
                    feedback.pushInfo(f"Layer moved to '{self.group()}' group")
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

    def _get_max_iter_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get max iteration counts and cell centers.
        Bypasses ras-commander GeoDataFrame creation to avoid CRS conflicts.
        """
        all_data = []
        proj_wkt = None
        
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                from ras_commander import HdfBase

                # 1. Get Projection
                proj_wkt = HdfBase.get_projection(hdf_path)

                # 2. Get Mesh Area Names
                flow_areas_path = "Geometry/2D Flow Areas"
                if flow_areas_path not in hdf_file: return None, None, []
                
                attributes = hdf_file[f"{flow_areas_path}/Attributes"][()]
                mesh_names = [name.decode('utf-8') for name in attributes["Name"]]

                # 3. Iterate through each mesh
                for mesh_name in mesh_names:
                    if feedback: feedback.pushInfo(f"Processing mesh: {mesh_name}")
                    
                    centers_path = f"Geometry/2D Flow Areas/{mesh_name}/Cells Center Coordinate"
                    if centers_path not in hdf_file: continue
                    cell_centers = hdf_file[centers_path][()]
                    
                    summary_path = f"Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/{mesh_name}/Cell Last Iteration"
                    if summary_path not in hdf_file: continue
                    
                    max_iter_data = hdf_file[summary_path][:]
                    
                    # 4. Combine data
                    for cell_id, center_coords in enumerate(cell_centers):
                        if cell_id < len(max_iter_data):
                            all_data.append({
                                'mesh_name': mesh_name,
                                'cell_id': cell_id,
                                'max_iter': int(max_iter_data[cell_id]),
                                'geometry_wkt': Point(center_coords).wkt  # Store WKT directly!
                            })
                
                if not all_data: return None, None, []
                
                df = pd.DataFrame(all_data)
                wkt_geometries = df['geometry_wkt'].tolist()  # Extract WKT list
                raw_df = df.drop(columns='geometry_wkt')  # Remove from DataFrame
                
                return proj_wkt, raw_df, wkt_geometries
        
        except Exception as e:
            raise QgsProcessingException(f"Error reading max iteration data directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            feedback.pushInfo("Using direct HDF access to avoid CRS conflicts...")
            proj_wkt, raw_df, wkt_geometries = self._get_max_iter_direct(hdf_path, feedback)

            if raw_df is None or raw_df.empty:
                raise QgsProcessingException("No maximum iteration count data found in the HDF file.")
            
            crs_name = "from HEC-RAS project" if proj_wkt else "Unknown"

        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed during initial data load: {e}")

        if proj_wkt:
            feedback.pushInfo(f"CRS found: {crs_name}")
        elif override_crs and override_crs.isValid():
            proj_wkt = override_crs.toWkt()
            feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
        else:
            raise QgsProcessingException(
                "Coordinate Reference System (CRS) could not be determined. "
                "Please define CRS in HEC-RAS or provide an Override CRS."
            )

        try:
            feedback.pushInfo("Reconstructing geometry within QGIS environment...")
            geometry = [loads(wkt) for wkt in wkt_geometries]
            gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)
            
        except Exception as e:
            raise QgsProcessingException(f"Failed during geometry reconstruction: {e}")

        fields = QgsFields()
        fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        fields.append(QgsField("cell_id", QMetaType.Type.Int))
        fields.append(QgsField("max_iter", QMetaType.Type.Int))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_LAYER, context, fields, QgsWkbTypes.Point, qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        total_features = len(gdf)
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled(): break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            feature.setAttribute("mesh_name", row['mesh_name'])
            feature.setAttribute("cell_id", int(row['cell_id']))
            feature.setAttribute("max_iter", int(row['max_iter']))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 2000 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled(): return {}

        return {self.OUTPUT_LAYER: dest_id}