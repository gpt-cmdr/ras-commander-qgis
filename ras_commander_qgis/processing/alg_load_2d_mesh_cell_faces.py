# ras_commander_qgis/processing/alg_load_2d_mesh_cell_faces.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
import h5py
import numpy as np
from shapely.geometry import LineString

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


class Load2DMeshCellFacesAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 2D mesh cell faces from a HEC-RAS geometry HDF file.
    
    This tool extracts individual 2D mesh cell faces and their
    attributes, and loads them as a line vector layer in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMeshCellFacesAlgorithm()

    def name(self):
        return 'load_2d_mesh_cell_faces'

    def displayName(self):
        return 'Load 2D Mesh Cell Faces'

    def group(self):
        return '2D Geometry Layers'

    def groupId(self):
        return 'ras_2d_geometry'

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
                '2D Mesh Cell Faces',
                QgsProcessing.TypeVectorLine
            )
        )

    def _get_mesh_area_names_direct(self, hdf_file):
        """Get mesh area names directly from HDF without CRS conflicts."""
        flow_areas_path = "Geometry/2D Flow Areas"
        if flow_areas_path not in hdf_file:
            return []
        
        attributes_path = f"{flow_areas_path}/Attributes"
        if attributes_path not in hdf_file:
            return []
        
        attributes = hdf_file[attributes_path][()]
        mesh_area_names = []
        for name in attributes["Name"]:
            if isinstance(name, bytes):
                mesh_area_names.append(name.decode('utf-8'))
            else:
                mesh_area_names.append(str(name))
        
        return mesh_area_names

    def _get_mesh_cell_faces_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get mesh cell faces without CRS conflicts.
        
        This bypasses the ras-commander GeoDataFrame creation to avoid pyproj conflicts.
        """
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                # Get projection information first
                from ras_commander import HdfBase
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Get mesh area names
                mesh_area_names = self._get_mesh_area_names_direct(hdf_file)
                if not mesh_area_names:
                    return None, None, []
                
                # Process each mesh to collect face data
                all_mesh_names = []
                all_face_ids = []
                wkt_geometries = []  # Store WKT strings, not geometry objects!

                for mesh_name in mesh_area_names:
                    try:
                        # Read all face data at once
                        facepoints_index = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces FacePoint Indexes"][()]
                        facepoints_coords = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/FacePoints Coordinate"][()]
                        faces_perim_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Info"][()]
                        faces_perim_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Values"][()]

                        # Process each face
                        for face_id, ((pnt_a_idx, pnt_b_idx), (start_row, count)) in enumerate(zip(facepoints_index, faces_perim_info)):
                            coords = [facepoints_coords[pnt_a_idx]]
                            
                            if count > 0:
                                coords.extend(faces_perim_values[start_row:start_row + count])
                                
                            coords.append(facepoints_coords[pnt_b_idx])
                            
                            all_mesh_names.append(mesh_name)
                            all_face_ids.append(face_id)
                            # Convert to WKT immediately - DO NOT create geometry object!
                            wkt_geometries.append(LineString(coords).wkt)
                            
                    except Exception as e:
                        if feedback:
                            feedback.pushInfo(f"Warning: Could not process faces for mesh '{mesh_name}': {e}")
                        continue

                if not wkt_geometries:
                    return None, None, []

                # Create raw data structure WITHOUT geometry column
                raw_data = {
                    'mesh_name': all_mesh_names,
                    'face_id': all_face_ids,
                }
                
                return proj_wkt, raw_data, wkt_geometries
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading mesh cell faces directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Direct HDF Access to Bypass ras-commander CRS Issues ---
            feedback.pushInfo(f"Loading mesh cell faces from {hdf_path}...")
            
            proj_wkt, raw_data, wkt_geometries = self._get_mesh_cell_faces_direct(hdf_path, feedback)
            
            if raw_data is None or len(wkt_geometries) == 0:
                raise QgsProcessingException("No mesh cell faces found in the HDF file.")
            
            # Create raw DataFrame (no geometry column yet)
            raw_df = pd.DataFrame({
                'mesh_name': raw_data['mesh_name'],
                'face_id': raw_data['face_id']
            })
            
            # Get CRS name for feedback (safely without using pyproj)
            crs_name = "Found in HEC-RAS project" if proj_wkt else "Unknown"
            
        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed during initial data load: {e}")

        # Check for CRS and apply override if necessary
        if proj_wkt:
            feedback.pushInfo(f"CRS {crs_name}")
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

        # Create fields for the output layer
        fields = QgsFields()
        fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        fields.append(QgsField("face_id", QMetaType.Type.Int))

        # Create QGIS CRS object
        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        # Get the feature sink
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_LAYER, context, fields,
            QgsWkbTypes.LineString, qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        # Process features
        total_features = len(gdf)
        feedback.pushInfo(f"Processing {total_features} mesh cell faces...")
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            # Set attributes
            feature.setAttribute("mesh_name", str(row['mesh_name']))
            feature.setAttribute("face_id", int(row['face_id']))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            # Update progress every 2000 features
            if i % 2000 == 0:
                progress = int((i / total_features) * 100)
                feedback.setProgress(progress)
                feedback.pushInfo(f"Processed {i+1} of {total_features} features...")
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully loaded {total_features} mesh cell faces")
        return {self.OUTPUT_LAYER: dest_id}