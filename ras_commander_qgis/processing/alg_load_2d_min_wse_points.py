# ras_commander_qgis/processing/alg_load_2d_min_wse_points.py
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

class Load2DMinimumWaterSurfacePointsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads minimum water surface elevation points from a HEC-RAS 2D results HDF file.
    
    This tool extracts the minimum water surface elevation at each 2D mesh cell
    center over the entire simulation period, and loads them as a point
    vector layer in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMinimumWaterSurfacePointsAlgorithm()

    def name(self):
        return 'load_2d_minimum_water_surface_points'

    def displayName(self):
        return 'Load 2D Min Water Surface Elevations at Cell Centers'

    def group(self):
        return '2D Summary Results'

    def groupId(self):
        return 'ras_2d_summary_results'

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
                    feedback.pushInfo(f"Minimum WSE Points layer moved to 'Benefit Area Analysis' group")
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

    def _get_min_wse_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get minimum water surface elevations and cell centers.
        Bypasses ras-commander GeoDataFrame creation to avoid CRS conflicts.
        """
        all_data = []
        proj_wkt = None
        
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                from ras_commander import HdfBase, HdfUtils

                # 1. Get Projection
                proj_wkt = HdfBase.get_projection(hdf_path)

                # 2. Get start time for timestamp conversion
                start_time = HdfBase.get_simulation_start_time(hdf_file)

                # 3. Get Mesh Area Names
                flow_areas_path = "Geometry/2D Flow Areas"
                if flow_areas_path not in hdf_file:
                    return None, None, []
                
                attributes = hdf_file[f"{flow_areas_path}/Attributes"][()]
                mesh_names = [name.decode('utf-8') if isinstance(name, bytes) else str(name) 
                             for name in attributes["Name"]]

                # 4. Iterate through each mesh
                for mesh_name in mesh_names:
                    if feedback:
                        feedback.pushInfo(f"Processing mesh: {mesh_name}")
                    
                    # Get cell centers
                    centers_path = f"Geometry/2D Flow Areas/{mesh_name}/Cells Center Coordinate"
                    if centers_path not in hdf_file:
                        continue
                    cell_centers = hdf_file[centers_path][()]
                    
                    # Get minimum water surface data
                    summary_path = f"Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/{mesh_name}/Minimum Water Surface"
                    if summary_path not in hdf_file:
                        continue
                    
                    data = hdf_file[summary_path][:]
                    
                    # Data should be 2D array: [values, times]
                    if data.ndim != 2 or data.shape[0] != 2:
                        if feedback:
                            feedback.pushInfo(f"Warning: Unexpected data shape for mesh '{mesh_name}': {data.shape}")
                        continue
                    
                    # 5. Combine data
                    for cell_id, center_coords in enumerate(cell_centers):
                        if cell_id < data.shape[1]:
                            # Convert time from days to datetime
                            time_of_min = HdfUtils.convert_timesteps_to_datetimes(
                                np.array([data[1, cell_id]]), start_time, time_unit="days"
                            )[0]
                            
                            all_data.append({
                                'mesh_name': mesh_name,
                                'cell_id': cell_id,
                                'min_wse': float(data[0, cell_id]),
                                'time_of_min': str(time_of_min),
                                'geometry_wkt': Point(center_coords).wkt  # Store WKT directly!
                            })
                
                if not all_data:
                    return None, None, []
                
                df = pd.DataFrame(all_data)
                wkt_geometries = df['geometry_wkt'].tolist()  # Extract WKT list
                raw_df = df.drop(columns='geometry_wkt')  # Remove from DataFrame
                
                return proj_wkt, raw_df, wkt_geometries
        
        except Exception as e:
            raise QgsProcessingException(f"Error reading min WSE data directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # Use direct HDF access to avoid CRS conflicts
            feedback.pushInfo("Using direct HDF access to avoid CRS conflicts...")
            proj_wkt, raw_df, wkt_geometries = self._get_min_wse_direct(hdf_path, feedback)

            if raw_df is None or raw_df.empty:
                raise QgsProcessingException("No minimum water surface data found in the HDF file.")
            
            crs_name = "from HEC-RAS project" if proj_wkt else "Unknown"

        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed during initial data load: {e}")

        # Check for CRS and apply override if necessary
        if proj_wkt:
            feedback.pushInfo(f"CRS found: {crs_name}")
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
            feedback.pushInfo("Reconstructing geometry within QGIS environment...")
            geometry = [loads(wkt) for wkt in wkt_geometries]
            gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)  # No CRS passed here!
            
        except Exception as e:
            raise QgsProcessingException(f"Failed during geometry reconstruction: {e}")

        # Proceed with Feature Sink pattern
        fields = QgsFields()
        fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        fields.append(QgsField("cell_id", QMetaType.Type.Int))
        fields.append(QgsField("min_wse", QMetaType.Type.Double))
        fields.append(QgsField("time_of_min", QMetaType.Type.QString))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_LAYER, context, fields,
            QgsWkbTypes.Point, qgis_crs
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
            
            feature.setAttribute("mesh_name", row['mesh_name'])
            feature.setAttribute("cell_id", int(row['cell_id']))
            feature.setAttribute("min_wse", float(row['min_wse']))
            feature.setAttribute("time_of_min", str(row['time_of_min']))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 2000 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        return {self.OUTPUT_LAYER: dest_id}