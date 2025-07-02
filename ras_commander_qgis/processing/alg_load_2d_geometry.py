# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
import h5py
import numpy as np
from shapely.geometry import Point, LineString, Polygon
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
    QgsProcessingParameterCrs,
    QgsProcessingParameterBoolean,
    QgsProcessingUtils
)
from PyQt5.QtCore import QMetaType
from .helpers import move_layer_to_group

class Load2DGeometryAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 2D geometry elements from a HEC-RAS geometry HDF file.
    
    This tool can extract various 2D geometry types including mesh area perimeters,
    mesh cells, cell faces, cell centers, breaklines, and boundary condition lines,
    loading them as appropriate vector layers in QGIS. Multiple geometry types can
    be selected at once.
    """
    INPUT_HDF = 'INPUT_HDF'
    LOAD_MESH_PERIMETERS = 'LOAD_MESH_PERIMETERS'
    LOAD_MESH_CELLS = 'LOAD_MESH_CELLS'
    LOAD_CELL_FACES = 'LOAD_CELL_FACES'
    LOAD_CELL_POINTS = 'LOAD_CELL_POINTS'
    LOAD_BREAKLINES = 'LOAD_BREAKLINES'
    LOAD_BC_LINES = 'LOAD_BC_LINES'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_MESH_PERIMETERS = 'OUTPUT_MESH_PERIMETERS'
    OUTPUT_MESH_CELLS = 'OUTPUT_MESH_CELLS'
    OUTPUT_CELL_FACES = 'OUTPUT_CELL_FACES'
    OUTPUT_CELL_POINTS = 'OUTPUT_CELL_POINTS'
    OUTPUT_BREAKLINES = 'OUTPUT_BREAKLINES'
    OUTPUT_BC_LINES = 'OUTPUT_BC_LINES'

    def createInstance(self):
        return Load2DGeometryAlgorithm()

    def name(self):
        return 'load_2d_geometry'

    def displayName(self):
        return 'Load 2D Geometry Elements'

    def group(self):
        return '2D Geometry Layers'

    def groupId(self):
        return 'ras_2d_geometry'

    def shortHelpString(self):
        return """
        <h3>Load 2D Geometry Elements</h3>
        <p>This algorithm loads various 2D geometry elements from a HEC-RAS geometry or plan HDF file.</p>
        
        <h4>Available Geometry Types (select one or more):</h4>
        <ul>
        <li><b>Mesh Area Perimeters:</b> 2D flow area boundary polygons</li>
        <li><b>Mesh Cells:</b> Individual 2D mesh cell polygons</li>
        <li><b>Cell Faces:</b> 2D mesh cell face lines</li>
        <li><b>Cell Centers:</b> 2D mesh cell center points</li>
        <li><b>Breaklines:</b> 2D mesh refinement lines</li>
        <li><b>Boundary Condition Lines:</b> 2D boundary condition lines</li>
        </ul>
        
        <h4>Parameters:</h4>
        <ul>
        <li><b>Geometry Types:</b> Select one or more types of 2D geometry to load. Each selected type will create a separate output layer.</li>
        <li><b>Override CRS:</b> Optional coordinate reference system to use if the HDF file lacks CRS information</li>
        </ul>
        
        <p><b>Note:</b> Loading mesh cells or cell faces for large models may take considerable time and memory.</p>
        """

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        """Post-process to move layers to appropriate groups."""
        results = super().postProcessAlgorithm(context, feedback) or {}
        
        # Move layers to appropriate groups
        group_mappings = {
            self.OUTPUT_MESH_PERIMETERS: ('Benefit Area Analysis', 'Mesh Area Perimeters'),
            self.OUTPUT_MESH_CELLS: ('2D Geometry Layers', 'Mesh Cells'),
            self.OUTPUT_CELL_FACES: ('2D Geometry Layers', 'Cell Faces'),
            self.OUTPUT_CELL_POINTS: ('2D Geometry Layers', 'Cell Centers'),
            self.OUTPUT_BREAKLINES: ('Benefit Area Analysis', 'Breaklines'),
            self.OUTPUT_BC_LINES: ('Benefit Area Analysis', 'Boundary Condition Lines')
        }
        
        for output_param, (group_name, layer_name) in group_mappings.items():
            if output_param in results and results[output_param]:
                layer_id = results[output_param]
                layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
                if layer:
                    success = move_layer_to_group(layer.id(), group_name)
                    if success:
                        feedback.pushInfo(f"{layer_name} layer moved to '{group_name}' group")
        
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
        
        # Add boolean parameters for each geometry type
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_MESH_PERIMETERS,
                'Load Mesh Area Perimeters',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_MESH_CELLS,
                'Load Mesh Cells (can be slow for large models)',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_CELL_FACES,
                'Load Cell Faces',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_CELL_POINTS,
                'Load Cell Centers',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_BREAKLINES,
                'Load Breaklines',
                defaultValue=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_BC_LINES,
                'Load Boundary Condition Lines',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterCrs(
                self.OVERRIDE_CRS,
                'Override CRS (Optional)',
                optional=True
            )
        )
        
        # Add output parameters for each geometry type
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_MESH_PERIMETERS,
                'Mesh Area Perimeters Output',
                type=QgsProcessing.TypeVectorPolygon,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_MESH_CELLS,
                'Mesh Cells Output',
                type=QgsProcessing.TypeVectorPolygon,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_CELL_FACES,
                'Cell Faces Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_CELL_POINTS,
                'Cell Centers Output',
                type=QgsProcessing.TypeVectorPoint,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_BREAKLINES,
                'Breaklines Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_BC_LINES,
                'Boundary Condition Lines Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
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

    def _load_mesh_perimeters(self, hdf_file, mesh_area_names, feedback):
        """Load mesh area perimeters from HDF file."""
        if not mesh_area_names:
            return None, []
        
        raw_data = {'mesh_name': []}
        wkt_geometries = []
        
        flow_areas_path = "Geometry/2D Flow Areas"
        for mesh_name in mesh_area_names:
            perimeter_path = f"{flow_areas_path}/{mesh_name}/Perimeter"
            if perimeter_path in hdf_file:
                perimeter_coords = hdf_file[perimeter_path][()]
                polygon_wkt = Polygon(perimeter_coords).wkt
                wkt_geometries.append(polygon_wkt)
                raw_data['mesh_name'].append(mesh_name)
            else:
                feedback.pushWarning(f"No perimeter found for mesh '{mesh_name}'")
        
        if not wkt_geometries:
            return None, []
        
        return raw_data, wkt_geometries

    def _load_mesh_cells(self, hdf_file, mesh_area_names, feedback):
        """Load mesh cells from HDF file."""
        if not mesh_area_names:
            return None, []
        
        # Get face geometries first
        face_geometries = self._get_mesh_cell_faces_for_cells(hdf_file, mesh_area_names, feedback)
        
        all_mesh_names = []
        all_cell_ids = []
        wkt_geometries = []

        for mesh_name in mesh_area_names:
            try:
                cell_face_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Cells Face and Orientation Info"][()]
                cell_face_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Cells Face and Orientation Values"][()][:, 0]
                
                mesh_faces = face_geometries.get(mesh_name, {})

                for cell_id, (start, length) in enumerate(cell_face_info[:, :2]):
                    face_ids = cell_face_values[start:start + length]
                    face_geoms = []
                    for face_id in face_ids:
                        if face_id in mesh_faces:
                            face_geoms.append(mesh_faces[face_id])
                    
                    if face_geoms:
                        try:
                            polygons = list(polygonize(face_geoms))
                            if polygons:
                                all_mesh_names.append(mesh_name)
                                all_cell_ids.append(cell_id)
                                wkt_geometries.append(polygons[0].wkt)
                        except Exception:
                            continue
            
            except Exception as e:
                if feedback:
                    feedback.pushWarning(f"Could not process cells for mesh '{mesh_name}': {e}")
                continue

        if not wkt_geometries:
            return None, []

        raw_data = {
            'mesh_name': all_mesh_names,
            'cell_id': all_cell_ids,
        }
        
        return raw_data, wkt_geometries

    def _get_mesh_cell_faces_for_cells(self, hdf_file, mesh_area_names, feedback=None):
        """Helper to get face geometries for cell construction."""
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
                if feedback:
                    feedback.pushWarning(f"Could not process faces for mesh '{mesh_name}': {e}")
                face_geometries[mesh_name] = {}
        
        return face_geometries

    def _load_cell_faces(self, hdf_file, mesh_area_names, feedback):
        """Load cell faces from HDF file."""
        if not mesh_area_names:
            return None, []
        
        all_mesh_names = []
        all_face_ids = []
        wkt_geometries = []

        for mesh_name in mesh_area_names:
            try:
                facepoints_index = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces FacePoint Indexes"][()]
                facepoints_coords = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/FacePoints Coordinate"][()]
                faces_perim_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Info"][()]
                faces_perim_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Values"][()]

                for face_id, ((pnt_a_idx, pnt_b_idx), (start_row, count)) in enumerate(zip(facepoints_index, faces_perim_info)):
                    coords = [facepoints_coords[pnt_a_idx]]
                    if count > 0:
                        coords.extend(faces_perim_values[start_row:start_row + count])
                    coords.append(facepoints_coords[pnt_b_idx])
                    
                    all_mesh_names.append(mesh_name)
                    all_face_ids.append(face_id)
                    wkt_geometries.append(LineString(coords).wkt)
                    
            except Exception as e:
                if feedback:
                    feedback.pushWarning(f"Could not process faces for mesh '{mesh_name}': {e}")
                continue

        if not wkt_geometries:
            return None, []

        raw_data = {
            'mesh_name': all_mesh_names,
            'face_id': all_face_ids,
        }
        
        return raw_data, wkt_geometries

    def _load_cell_points(self, hdf_file, mesh_area_names, feedback):
        """Load cell center points from HDF file."""
        if not mesh_area_names:
            return None, []
        
        all_mesh_names = []
        all_cell_ids = []
        wkt_geometries = []

        for mesh_name in mesh_area_names:
            try:
                cell_centers_path = f"Geometry/2D Flow Areas/{mesh_name}/Cells Center Coordinate"
                if cell_centers_path not in hdf_file:
                    if feedback:
                        feedback.pushWarning(f"No cell centers found for mesh '{mesh_name}'")
                    continue
                    
                cell_centers = hdf_file[cell_centers_path][()]
                
                for cell_id, center_coords in enumerate(cell_centers):
                    all_mesh_names.append(mesh_name)
                    all_cell_ids.append(cell_id)
                    wkt_geometries.append(Point(center_coords).wkt)
                    
            except Exception as e:
                if feedback:
                    feedback.pushWarning(f"Could not process cell centers for mesh '{mesh_name}': {e}")
                continue

        if not wkt_geometries:
            return None, []

        raw_data = {
            'mesh_name': all_mesh_names,
            'cell_id': all_cell_ids,
        }
        
        return raw_data, wkt_geometries

    def _load_breaklines(self, hdf_file, feedback):
        """Load breaklines from HDF file."""
        breaklines_path = "Geometry/2D Flow Area Break Lines"
        if breaklines_path not in hdf_file:
            return None, []
        
        bl_line_data = hdf_file[breaklines_path]
        attributes = bl_line_data["Attributes"][()]
        
        valid_ids = []
        valid_names = []
        wkt_geometries = []

        for idx, (pnt_start, pnt_cnt, part_start, part_cnt) in enumerate(bl_line_data["Polyline Info"][()]):
            name = attributes["Name"][idx]
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            else:
                name = str(name)

            if pnt_cnt < 2:
                continue

            try:
                points = bl_line_data["Polyline Points"][()][pnt_start:pnt_start + pnt_cnt]
                
                if part_cnt == 1:
                    geom = LineString(points)
                else:
                    parts = bl_line_data["Polyline Parts"][()][part_start:part_start + part_cnt]
                    line_parts = []
                    for part_pnt_start, part_pnt_cnt in parts:
                        if part_pnt_cnt > 1:
                            part_points = points[part_pnt_start:part_pnt_start + part_pnt_cnt]
                            line_parts.append(LineString(part_points))
                    
                    if not line_parts:
                        continue
                    
                    geom = line_parts[0]  # Simplify to single line

                valid_ids.append(idx)
                valid_names.append(name)
                wkt_geometries.append(geom.wkt)

            except Exception:
                continue

        if not wkt_geometries:
            return None, []

        raw_data = {
            'bl_id': valid_ids,
            'Name': valid_names,
        }
        
        return raw_data, wkt_geometries

    def _load_bc_lines(self, hdf_file, feedback):
        """Load boundary condition lines from HDF file."""
        bc_lines_path = "Geometry/Boundary Condition Lines"
        if bc_lines_path not in hdf_file:
            return None, []
        
        bc_attrs = hdf_file[f"{bc_lines_path}/Attributes"][()]
        bc_names = [name.decode('utf-8') if isinstance(name, bytes) else str(name) 
                   for name in bc_attrs["Name"]]
        bc_types = [typename.decode('utf-8') if isinstance(typename, bytes) else str(typename) 
                   for typename in bc_attrs["Type"]]
        
        polyline_info = hdf_file[f"{bc_lines_path}/Polyline Info"][()]
        polyline_parts = hdf_file[f"{bc_lines_path}/Polyline Parts"][()]
        polyline_points = hdf_file[f"{bc_lines_path}/Polyline Points"][()]
        
        wkt_geometries = []
        for pnt_start, pnt_cnt, part_start, part_cnt in polyline_info:
            points = polyline_points[pnt_start : pnt_start + pnt_cnt]
            if part_cnt == 1:
                line_wkt = LineString(points).wkt
                wkt_geometries.append(line_wkt)
            else:
                parts = polyline_parts[part_start : part_start + part_cnt]
                line_parts = []
                for part_pnt_start, part_pnt_cnt in parts:
                    part_points = points[part_pnt_start : part_pnt_start + part_pnt_cnt]
                    line_parts.append(LineString(part_points))
                line_wkt = line_parts[0].wkt if line_parts else LineString([]).wkt
                wkt_geometries.append(line_wkt)
        
        raw_data = {
            'Name': bc_names,
            'Type': bc_types,
        }
        
        return raw_data, wkt_geometries

    def _get_fields_for_geometry_type(self, geom_type):
        """Get the appropriate fields definition for each geometry type."""
        fields = QgsFields()
        
        if geom_type == 'mesh_perimeters':
            fields.append(QgsField("mesh_name", QMetaType.Type.QString))
            
        elif geom_type in ['mesh_cells', 'cell_points']:
            fields.append(QgsField("mesh_name", QMetaType.Type.QString))
            fields.append(QgsField("cell_id", QMetaType.Type.Int))
            
        elif geom_type == 'cell_faces':
            fields.append(QgsField("mesh_name", QMetaType.Type.QString))
            fields.append(QgsField("face_id", QMetaType.Type.Int))
            
        elif geom_type == 'breaklines':
            fields.append(QgsField("bl_id", QMetaType.Type.Int))
            fields.append(QgsField("Name", QMetaType.Type.QString))
            
        elif geom_type == 'bc_lines':
            fields.append(QgsField("Name", QMetaType.Type.QString))
            fields.append(QgsField("Type", QMetaType.Type.QString))
        
        return fields

    def _process_geometry_type(self, raw_data, wkt_geometries, geom_type, wkb_type, 
                              proj_wkt, parameters, context, feedback):
        """Process a single geometry type and return the output layer ID."""
        if raw_data is None or not wkt_geometries:
            return None
        
        # Reconstruct GeoDataFrame
        try:
            geometry = [loads(wkt) for wkt in wkt_geometries]
            gdf = gpd.GeoDataFrame(raw_data, geometry=geometry)
        except Exception as e:
            feedback.pushWarning(f"Failed to reconstruct geometry for {geom_type}: {e}")
            return None

        # Get appropriate fields
        fields = self._get_fields_for_geometry_type(geom_type)
        
        # Create QGIS CRS object
        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        # Map geometry type to output parameter
        output_param_map = {
            'mesh_perimeters': self.OUTPUT_MESH_PERIMETERS,
            'mesh_cells': self.OUTPUT_MESH_CELLS,
            'cell_faces': self.OUTPUT_CELL_FACES,
            'cell_points': self.OUTPUT_CELL_POINTS,
            'breaklines': self.OUTPUT_BREAKLINES,
            'bc_lines': self.OUTPUT_BC_LINES
        }
        
        output_param = output_param_map[geom_type]
        
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            output_param,
            context,
            fields,
            wkb_type,
            qgis_crs
        )

        if sink is None:
            return None

        # Add features
        total_features = len(gdf)
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            # Set attributes
            for field in fields:
                col_name = field.name()
                if col_name in row:
                    value = row[col_name]
                    if pd.notna(value):
                        if isinstance(value, (np.integer, int)):
                            feature.setAttribute(col_name, int(value))
                        elif isinstance(value, (np.floating, float)):
                            feature.setAttribute(col_name, float(value))
                        else:
                            feature.setAttribute(col_name, str(value))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

        return dest_id

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)
        
        # Check which geometry types to load
        load_mesh_perimeters = self.parameterAsBoolean(parameters, self.LOAD_MESH_PERIMETERS, context)
        load_mesh_cells = self.parameterAsBoolean(parameters, self.LOAD_MESH_CELLS, context)
        load_cell_faces = self.parameterAsBoolean(parameters, self.LOAD_CELL_FACES, context)
        load_cell_points = self.parameterAsBoolean(parameters, self.LOAD_CELL_POINTS, context)
        load_breaklines = self.parameterAsBoolean(parameters, self.LOAD_BREAKLINES, context)
        load_bc_lines = self.parameterAsBoolean(parameters, self.LOAD_BC_LINES, context)
        
        # Check if at least one geometry type is selected
        if not any([load_mesh_perimeters, load_mesh_cells, load_cell_faces, 
                   load_cell_points, load_breaklines, load_bc_lines]):
            raise QgsProcessingException("Please select at least one geometry type to load.")
        
        # Get projection from HDF
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                from ras_commander import HdfBase
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Get mesh area names (needed for most operations)
                mesh_area_names = self._get_mesh_area_names_direct(hdf_file)
                
                # Determine CRS
                if proj_wkt:
                    feedback.pushInfo("CRS found in HEC-RAS project")
                elif override_crs and override_crs.isValid():
                    proj_wkt = override_crs.toWkt()
                    feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
                else:
                    raise QgsProcessingException(
                        "Coordinate Reference System (CRS) could not be determined. "
                        "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                        "or provide a valid Override CRS in the tool dialog."
                    )
                
                results = {}
                total_steps = sum([load_mesh_perimeters, load_mesh_cells, load_cell_faces,
                                 load_cell_points, load_breaklines, load_bc_lines])
                current_step = 0
                
                # Process each selected geometry type
                if load_mesh_perimeters:
                    feedback.pushInfo("Loading mesh area perimeters...")
                    raw_data, wkt_geoms = self._load_mesh_perimeters(hdf_file, mesh_area_names, feedback)
                    if raw_data:
                        dest_id = self._process_geometry_type(
                            raw_data, wkt_geoms, 'mesh_perimeters', QgsWkbTypes.Polygon,
                            proj_wkt, parameters, context, feedback
                        )
                        if dest_id:
                            results[self.OUTPUT_MESH_PERIMETERS] = dest_id
                            feedback.pushInfo(f"Successfully loaded {len(wkt_geoms)} mesh area perimeters.")
                    current_step += 1
                    feedback.setProgress(int((current_step / total_steps) * 100))
                
                if load_mesh_cells:
                    feedback.pushInfo("Loading mesh cells (this may take a while)...")
                    raw_data, wkt_geoms = self._load_mesh_cells(hdf_file, mesh_area_names, feedback)
                    if raw_data:
                        dest_id = self._process_geometry_type(
                            raw_data, wkt_geoms, 'mesh_cells', QgsWkbTypes.Polygon,
                            proj_wkt, parameters, context, feedback
                        )
                        if dest_id:
                            results[self.OUTPUT_MESH_CELLS] = dest_id
                            feedback.pushInfo(f"Successfully loaded {len(wkt_geoms)} mesh cells.")
                    current_step += 1
                    feedback.setProgress(int((current_step / total_steps) * 100))
                
                if load_cell_faces:
                    feedback.pushInfo("Loading cell faces...")
                    raw_data, wkt_geoms = self._load_cell_faces(hdf_file, mesh_area_names, feedback)
                    if raw_data:
                        dest_id = self._process_geometry_type(
                            raw_data, wkt_geoms, 'cell_faces', QgsWkbTypes.LineString,
                            proj_wkt, parameters, context, feedback
                        )
                        if dest_id:
                            results[self.OUTPUT_CELL_FACES] = dest_id
                            feedback.pushInfo(f"Successfully loaded {len(wkt_geoms)} cell faces.")
                    current_step += 1
                    feedback.setProgress(int((current_step / total_steps) * 100))
                
                if load_cell_points:
                    feedback.pushInfo("Loading cell centers...")
                    raw_data, wkt_geoms = self._load_cell_points(hdf_file, mesh_area_names, feedback)
                    if raw_data:
                        dest_id = self._process_geometry_type(
                            raw_data, wkt_geoms, 'cell_points', QgsWkbTypes.Point,
                            proj_wkt, parameters, context, feedback
                        )
                        if dest_id:
                            results[self.OUTPUT_CELL_POINTS] = dest_id
                            feedback.pushInfo(f"Successfully loaded {len(wkt_geoms)} cell centers.")
                    current_step += 1
                    feedback.setProgress(int((current_step / total_steps) * 100))
                
                if load_breaklines:
                    feedback.pushInfo("Loading breaklines...")
                    raw_data, wkt_geoms = self._load_breaklines(hdf_file, feedback)
                    if raw_data:
                        dest_id = self._process_geometry_type(
                            raw_data, wkt_geoms, 'breaklines', QgsWkbTypes.LineString,
                            proj_wkt, parameters, context, feedback
                        )
                        if dest_id:
                            results[self.OUTPUT_BREAKLINES] = dest_id
                            feedback.pushInfo(f"Successfully loaded {len(wkt_geoms)} breaklines.")
                    current_step += 1
                    feedback.setProgress(int((current_step / total_steps) * 100))
                
                if load_bc_lines:
                    feedback.pushInfo("Loading boundary condition lines...")
                    raw_data, wkt_geoms = self._load_bc_lines(hdf_file, feedback)
                    if raw_data:
                        dest_id = self._process_geometry_type(
                            raw_data, wkt_geoms, 'bc_lines', QgsWkbTypes.LineString,
                            proj_wkt, parameters, context, feedback
                        )
                        if dest_id:
                            results[self.OUTPUT_BC_LINES] = dest_id
                            feedback.pushInfo(f"Successfully loaded {len(wkt_geoms)} boundary condition lines.")
                    current_step += 1
                    feedback.setProgress(int((current_step / total_steps) * 100))
                
                if not results:
                    raise QgsProcessingException("No geometry data could be loaded from the HDF file.")
                
                return results
                
        except Exception as e:
            raise QgsProcessingException(f"Failed to process HDF file: {e}")