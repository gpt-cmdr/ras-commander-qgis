# ras_commander_qgis/processing/alg_load_2d_max_face_velocity_points.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point, LineString
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
    QgsProcessingUtils
)
from PyQt5.QtCore import QMetaType

class Load2DMaxFaceVelocityPointsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads maximum face velocity from a HEC-RAS 2D results HDF file.
    
    This tool extracts the maximum velocity at each 2D mesh face over 
    the simulation period, and loads them as a point layer at the face
    centers in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMaxFaceVelocityPointsAlgorithm()

    def name(self):
        return 'load_2d_max_face_velocity_points'

    def displayName(self):
        return 'Load 2D Max Face Velocity at Face Centers'

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

    def _get_mesh_cell_faces_direct(self, hdf_file, mesh_area_names, feedback=None):
        """Helper to get face LineString geometries directly from HDF."""
        face_geometries = {}
        for mesh_name in mesh_area_names:
            try:
                facepoints_index = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces FacePoint Indexes"][()]
                facepoints_coords = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/FacePoints Coordinate"][()]
                faces_perim_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Info"][()]
                faces_perim_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Values"][()]

                mesh_faces = {}
                for face_id, ((pnt_a_idx, pnt_b_idx), (start_row, count)) in enumerate(zip(facepoints_index, faces_perim_info)):
                    coords = [facepoints_coords[pnt_a_idx]]
                    if count > 0:
                        coords.extend(faces_perim_values[start_row:start_row + count])
                    coords.append(facepoints_coords[pnt_b_idx])
                    mesh_faces[face_id] = LineString(coords)
                
                face_geometries[mesh_name] = mesh_faces
            except Exception as e:
                if feedback: feedback.pushInfo(f"Warning: Could not process faces for mesh '{mesh_name}': {e}")
                face_geometries[mesh_name] = {}
        return face_geometries

    def _get_max_face_vel_direct(self, hdf_path, feedback=None):
        """Direct HDF access to get max face velocities and face centers."""
        all_data = []
        proj_wkt = None
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                from ras_commander import HdfBase, HdfUtils

                proj_wkt = HdfBase.get_projection(hdf_path)
                
                flow_areas_path = "Geometry/2D Flow Areas"
                if flow_areas_path not in hdf_file: return None, None, []
                attributes = hdf_file[f"{flow_areas_path}/Attributes"][()]
                mesh_names = [name.decode('utf-8') for name in attributes["Name"]]

                start_time = HdfBase.get_simulation_start_time(hdf_file)
                face_geoms = self._get_mesh_cell_faces_direct(hdf_file, mesh_names, feedback)

                for mesh_name in mesh_names:
                    if feedback: feedback.pushInfo(f"Processing mesh: {mesh_name}")
                    
                    if not face_geoms.get(mesh_name): continue

                    summary_path = f"Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/{mesh_name}/Maximum Face Velocity"
                    if summary_path not in hdf_file: continue
                    
                    data = hdf_file[summary_path][:] # 2D array: [values, times]
                    
                    for face_id in range(data.shape[1]):
                        if face_id in face_geoms[mesh_name]:
                            face_line = face_geoms[mesh_name][face_id]
                            time_of_max_days = data[1, face_id]
                            time_of_max = HdfUtils.convert_timesteps_to_datetimes(
                                np.array([time_of_max_days]), start_time, time_unit="days"
                            )[0]

                            all_data.append({
                                'mesh_name': mesh_name,
                                'face_id': face_id,
                                'max_vel': float(data[0, face_id]),
                                'time_of_max': str(time_of_max),
                                'geometry_wkt': face_line.centroid.wkt  # Store WKT directly!
                            })

                if not all_data: return None, None, []
                
                df = pd.DataFrame(all_data)
                wkt_geometries = df['geometry_wkt'].tolist()  # Extract WKT list
                raw_df = df.drop(columns='geometry_wkt')  # Remove from DataFrame

                return proj_wkt, raw_df, wkt_geometries
        except Exception as e:
            raise QgsProcessingException(f"Error reading max face velocity data directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            feedback.pushInfo("Using direct HDF access to avoid CRS conflicts...")
            proj_wkt, raw_df, wkt_geometries = self._get_max_face_vel_direct(hdf_path, feedback)

            if raw_df is None or raw_df.empty:
                raise QgsProcessingException("No maximum face velocity data found in the HDF file.")
            
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
        fields.append(QgsField("face_id", QMetaType.Type.Int))
        fields.append(QgsField("max_vel", QMetaType.Type.Double))
        fields.append(QgsField("time_of_max", QMetaType.Type.QString))

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
            feature.setAttribute("face_id", int(row['face_id']))
            feature.setAttribute("max_vel", float(row['max_vel']))
            feature.setAttribute("time_of_max", str(row['time_of_max']))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 2000 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled(): return {}

        return {self.OUTPUT_LAYER: dest_id}