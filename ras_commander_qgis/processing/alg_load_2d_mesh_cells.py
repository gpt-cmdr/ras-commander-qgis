# ras_commander_qgis/processing/alg_load_2d_mesh_cells.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
import h5py
import numpy as np
from shapely.geometry import Polygon, LineString
from shapely.ops import polygonize

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

class Load2DMeshCellsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 2D mesh cells from a HEC-RAS geometry HDF file.
    
    This tool extracts individual 2D mesh cell polygons and their
    attributes, and loads them as a polygon vector layer in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMeshCellsAlgorithm()

    def name(self):
        return 'load_2d_mesh_cells'

    def displayName(self):
        return 'Load 2D Mesh Cells as Polygons'

    def group(self):
        return '2D Geometry Layers'

    def groupId(self):
        return 'ras_2d_geometry'

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
                '2D Mesh Cells',
                QgsProcessing.TypeVectorPolygon
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

    def _get_mesh_cell_faces_direct(self, hdf_file, mesh_area_names, feedback=None):
        """Get mesh cell faces directly from HDF without CRS conflicts."""
        face_geometries = {}  # mesh_name -> {face_id: LineString}
        
        for mesh_name in mesh_area_names:
            try:
                # Read all face data at once
                facepoints_index = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces FacePoint Indexes"][()]
                facepoints_coords = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/FacePoints Coordinate"][()]
                faces_perim_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Info"][()]
                faces_perim_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Values"][()]

                mesh_faces = {}
                # Process each face
                for face_id, ((pnt_a_idx, pnt_b_idx), (start_row, count)) in enumerate(zip(facepoints_index, faces_perim_info)):
                    coords = [facepoints_coords[pnt_a_idx]]
                    
                    if count > 0:
                        coords.extend(faces_perim_values[start_row:start_row + count])
                        
                    coords.append(facepoints_coords[pnt_b_idx])
                    mesh_faces[face_id] = LineString(coords)
                
                face_geometries[mesh_name] = mesh_faces
                
            except Exception as e:
                if feedback:
                    feedback.pushInfo(f"Warning: Could not process faces for mesh '{mesh_name}': {e}")
                face_geometries[mesh_name] = {}
        
        return face_geometries

    def _get_mesh_cells_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get mesh cells without CRS conflicts.
        
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
                
                # Get face geometries for all meshes
                face_geometries = self._get_mesh_cell_faces_direct(hdf_file, mesh_area_names, feedback)
                
                # Process each mesh to create cell polygons
                all_mesh_names = []
                all_cell_ids = []
                wkt_geometries = []  # Store WKT strings, not geometry objects!

                for mesh_name in mesh_area_names:
                    try:
                        # Get cell face info
                        cell_face_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Cells Face and Orientation Info"][()]
                        cell_face_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Cells Face and Orientation Values"][()][:, 0]
                        
                        # Get face lookup for this mesh
                        mesh_faces = face_geometries.get(mesh_name, {})

                        # Process each cell
                        for cell_id, (start, length) in enumerate(cell_face_info[:, :2]):
                            face_ids = cell_face_values[start:start + length]
                            face_geoms = []
                            for face_id in face_ids:
                                if face_id in mesh_faces:
                                    face_geoms.append(mesh_faces[face_id])
                            
                            # Create polygon from faces
                            if face_geoms:
                                try:
                                    polygons = list(polygonize(face_geoms))
                                    if polygons:
                                        all_mesh_names.append(mesh_name)
                                        all_cell_ids.append(cell_id)
                                        # Convert to WKT immediately!
                                        wkt_geometries.append(polygons[0].wkt)
                                except Exception as e:
                                    # Skip cells that can't be polygonized
                                    continue
                    
                    except Exception as e:
                        if feedback:
                            feedback.pushInfo(f"Warning: Could not process cells for mesh '{mesh_name}': {e}")
                        continue

                if not wkt_geometries:
                    return None, None, []

                # Create raw data structure WITHOUT geometry column
                raw_data = {
                    'mesh_name': all_mesh_names,
                    'cell_id': all_cell_ids,
                }
                
                return proj_wkt, raw_data, wkt_geometries
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading mesh cells directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Direct HDF Access to Bypass ras-commander CRS Issues ---
            feedback.pushInfo(f"Loading mesh cells from {hdf_path}...")
            
            proj_wkt, raw_data, wkt_geometries = self._get_mesh_cells_direct(hdf_path, feedback)
            
            if raw_data is None or len(raw_data.get('mesh_name', [])) == 0:
                raise QgsProcessingException("No mesh cells found in the HDF file.")
            
            # Create raw DataFrame (no geometry column yet)
            raw_df = pd.DataFrame({
                'mesh_name': raw_data['mesh_name'],
                'cell_id': raw_data['cell_id']
            })
            
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
        fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        fields.append(QgsField("cell_id", QMetaType.Type.Int))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            fields,
            QgsWkbTypes.Polygon,
            qgis_crs
        )

        if sink is None:
            raise QgsProcessingException(f"Could not create sink for output layer '{self.OUTPUT_LAYER}'.")

        total_features = len(gdf)
        feedback.pushInfo(f"Processing {total_features} mesh cells...")
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break

            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            feature.setAttribute("mesh_name", str(row.mesh_name))
            feature.setAttribute("cell_id", int(row.cell_id))

            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            if i % 2000 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully processed {total_features} mesh cells")
        return {self.OUTPUT_LAYER: dest_id}