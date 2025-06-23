# ras_commander_qgis/processing/alg_load_2d_max_wse_points.py
# -*- coding: utf-8 -*-

"""
QGIS Processing anaylsis to extract Maximum Water Surface data from a HEC-RAS HDF file.
This algorithm is self-contained and uses h5py directly, without depending on the
ras-commander library.
"""

# Standard library imports
from datetime import datetime, timedelta

# Third-party imports
import h5py
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# QGIS and PyQt imports
from qgis.PyQt.QtCore import QCoreApplication, QMetaType
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterCrs,
    QgsProcessing,
    QgsProcessingException,
    QgsFields,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsFeatureSink,
    QgsProcessingUtils
)


class Load2DMaximumWaterSurfacePointsAlgorithm(QgsProcessingAlgorithm):
    """
    This algorithm loads the Maximum Water Surface Elevation for each 2D mesh
    cell from a HEC-RAS results HDF file (*.p##.hdf).

    It creates a point vector layer where each point represents the center of a
    2D cell, with attributes for the maximum water surface, the time it occurred,
    and the cell identifier.
    """

    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMaximumWaterSurfacePointsAlgorithm()

    def name(self):
        return 'load_2d_maximum_water_surface_points'

    def displayName(self):
        return self.tr('Load 2D Max Water Surface Elevations at Cell Centers')

    def group(self):
        return self.tr('2D Summary Results')

    def groupId(self):
        return 'ras_2d_summary_results'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def postProcessAlgorithm(self, context, feedback):
        results = super().postProcessAlgorithm(context, feedback) or {}
        if self.OUTPUT_LAYER in results:
            layer_id = results[self.OUTPUT_LAYER]
            layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
            if layer:
                from .helpers import move_layer_to_benefit_area_group
                success = move_layer_to_benefit_area_group(layer.id())
                if success:
                    feedback.pushInfo(self.tr("Maximum WSE Points layer moved to 'Benefit Area Analysis' group"))
        return results

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_HDF,
                self.tr('HEC-RAS Plan HDF File (*.p##.hdf)'),
                behavior=QgsProcessingParameterFile.File,
                fileFilter='HEC-RAS HDF Results Files (*.p*.hdf *.hdf)'
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.OVERRIDE_CRS,
                self.tr('Override CRS (Optional)'),
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                self.tr('Maximum Water Surface'),
                QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        all_cell_data = []
        proj_wkt = None

        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                feedback.pushInfo(self.tr('Reading HDF file...'))

                if 'Projection' in hdf_file.attrs:
                    proj_wkt_bytes = hdf_file.attrs['Projection']
                    proj_wkt = proj_wkt_bytes.decode('utf-8')
                    feedback.pushInfo(self.tr('Found Coordinate Reference System in HDF file.'))

                plan_info = hdf_file.get("Plan Data/Plan Information")
                if plan_info is None or 'Simulation Start Time' not in plan_info.attrs:
                    raise QgsProcessingException(self.tr("Could not find 'Simulation Start Time' in HDF file."))
                
                time_str_bytes = plan_info.attrs['Simulation Start Time']
                start_time = datetime.strptime(time_str_bytes.decode('utf-8'), "%d%b%Y %H:%M:%S")
                feedback.pushInfo(self.tr(f'Simulation start time: {start_time}'))

                flow_areas_path = "Geometry/2D Flow Areas"
                if f"{flow_areas_path}/Attributes" not in hdf_file:
                    raise QgsProcessingException(self.tr("No 2D Flow Areas found in HDF file."))
                
                attributes_ds = hdf_file[f"{flow_areas_path}/Attributes"]
                mesh_names = [name.decode('utf-8').strip() for name in attributes_ds["Name"]]

                for mesh_name in mesh_names:
                    feedback.pushInfo(self.tr(f'Processing mesh: {mesh_name}'))

                    centers_path = f"Geometry/2D Flow Areas/{mesh_name}/Cells Center Coordinate"
                    if centers_path not in hdf_file:
                        feedback.pushInfo(self.tr(f"Warning: No cell centers found for mesh '{mesh_name}'. Skipping."))
                        continue
                    cell_centers = hdf_file[centers_path][()]

                    summary_path = f"Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/{mesh_name}/Maximum Water Surface"
                    if summary_path not in hdf_file:
                        feedback.pushInfo(self.tr(f"Warning: No 'Maximum Water Surface' data for mesh '{mesh_name}'. Skipping."))
                        continue
                    
                    max_wse_data = hdf_file[summary_path][:]
                    wse_values = max_wse_data[0, :]
                    time_in_days = max_wse_data[1, :]

                    num_cells = len(cell_centers)
                    for i in range(num_cells):
                        if i >= len(wse_values):
                            feedback.pushInfo(self.tr(f"Warning: Data array length mismatch for cell {i} in mesh '{mesh_name}'. Skipping."))
                            break
                        
                        time_of_max = start_time + timedelta(days=float(time_in_days[i]))
                        
                        all_cell_data.append({
                            'Mesh': mesh_name,
                            'Cell': i,
                            'WSEL': float(wse_values[i]),
                            'Time': time_of_max,
                            'geometry': Point(cell_centers[i])
                        })

        except IOError:
            raise QgsProcessingException(self.tr(f"Could not open HDF file: {hdf_path}"))
        except Exception as e:
            raise QgsProcessingException(self.tr(f"An error occurred while reading the HDF file: {e}"))

        if not all_cell_data:
            raise QgsProcessingException(self.tr("No 'Maximum Water Surface' data could be extracted from the HDF file."))

        feedback.pushInfo(self.tr('Creating features...'))
        gdf = gpd.GeoDataFrame(all_cell_data, geometry='geometry')

        if proj_wkt:
            qgis_crs = QgsCoordinateReferenceSystem(proj_wkt)
        elif override_crs and override_crs.isValid():
            feedback.pushInfo(self.tr(f'Using user-provided override CRS: {override_crs.authid()}'))
            qgis_crs = override_crs
        else:
            raise QgsProcessingException(
                self.tr("Coordinate Reference System could not be determined. "
                        "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                        "or provide a valid Override CRS in the tool dialog.")
            )

        # --- FIX: Define the Time field as a String ---
        fields = QgsFields()
        fields.append(QgsField("Mesh", QMetaType.Type.QString))
        fields.append(QgsField("Cell", QMetaType.Type.Int))
        fields.append(QgsField("WSEL", QMetaType.Type.Double))
        fields.append(QgsField("Time", QMetaType.Type.QString))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.Point,
            qgis_crs
        )
        
        if sink is None:
             raise QgsProcessingException(self.tr("Could not create sink for output layer."))

        total_features = len(gdf)
        feedback.pushInfo(self.tr(f'Writing {total_features} features to layer...'))

        for index, row in gdf.iterrows():
            if feedback.isCanceled():
                break

            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            feature.setAttribute("Mesh", row['Mesh'])
            feature.setAttribute("Cell", int(row['Cell']))
            feature.setAttribute("WSEL", float(row['WSEL']))
            
            # --- FIX: Format the datetime object into an ISO-like string ---
            # This ensures it is treated as simple text and avoids timezone issues.
            py_dt = row['Time']
            time_str = py_dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] # Format with milliseconds
            feature.setAttribute("Time", time_str)
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if index % 1000 == 0:
                feedback.setProgress(int(index / total_features * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(self.tr('Maximum Water Surface layer created successfully.'))
        return {self.OUTPUT_LAYER: dest_id}