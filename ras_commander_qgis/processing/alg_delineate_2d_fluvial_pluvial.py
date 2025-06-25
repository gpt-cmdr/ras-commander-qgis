# ras_commander_qgis/processing/alg_delineate_2d_fluvial_pluvial.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon
from shapely.ops import unary_union
from collections import defaultdict
import numpy as np
import h5py

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterEnum,
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

class Delineate2DFluvialPluvialBoundaryAlgorithm(QgsProcessingAlgorithm):
    """
    Delineates the fluvial-pluvial boundary or areas from a HEC-RAS results HDF file.
    
    This tool analyzes the timing of flood arrival to distinguish between
    fluvial (river-driven) and pluvial (rainfall-driven) flooding areas
    based on a specified time threshold. It can output either:
    - Boundary lines between fluvial and pluvial areas
    - Polygon areas showing fluvial and pluvial zones
    """
    INPUT_HDF = 'INPUT_HDF'
    OUTPUT_TYPE = 'OUTPUT_TYPE'
    TIME_THRESHOLD = 'TIME_THRESHOLD'
    MIN_SEGMENT_LENGTH = 'MIN_SEGMENT_LENGTH'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'
    OUTPUT_FLUVIAL_AREAS = 'OUTPUT_FLUVIAL_AREAS'
    OUTPUT_PLUVIAL_AREAS = 'OUTPUT_PLUVIAL_AREAS'

    def createInstance(self):
        return Delineate2DFluvialPluvialBoundaryAlgorithm()

    def name(self):
        return 'delineate_fluvial_pluvial_boundary'

    def displayName(self):
        return 'Delineate Fluvial-Pluvial Boundary/Areas'

    def group(self):
        return 'Analysis Algorithms'

    def groupId(self):
        return 'ras_analysis'

    def shortHelpString(self):
        return """
        <h3>Delineate Fluvial-Pluvial Boundary/Areas</h3>
        <p>This algorithm analyzes the timing of flood arrival to distinguish between fluvial (river-driven) 
        and pluvial (rainfall-driven) flooding based on a specified time threshold (delta_t).</p>
        
        <h4>Output Options:</h4>
        <ul>
        <li><b>Boundary Lines:</b> Creates line features representing the boundary between fluvial and pluvial areas</li>
        <li><b>Area Polygons:</b> Creates polygon features showing the full extent of fluvial and pluvial zones</li>
        </ul>
        
        <h4>Parameters:</h4>
        <ul>
        <li><b>Time Threshold (delta_t):</b> Hours that define the cutoff between fluvial and pluvial flooding. 
        Areas that flood before this threshold are considered fluvial, after are considered pluvial.</li>
        <li><b>Minimum Segment Length:</b> For boundary lines only - removes short segments to clean up the output</li>
        </ul>
        """

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        """Post-process to move the created layer to the Benefit Area Analysis group."""
        results = super().postProcessAlgorithm(context, feedback) or {}
        
        # Move the output layer(s) to the Benefit Area Analysis group
        outputs_to_move = []
        if self.OUTPUT_LAYER in results:
            outputs_to_move.append((results[self.OUTPUT_LAYER], "Fluvial-Pluvial Boundary"))
        if self.OUTPUT_FLUVIAL_AREAS in results:
            outputs_to_move.append((results[self.OUTPUT_FLUVIAL_AREAS], "Fluvial Areas"))
        if self.OUTPUT_PLUVIAL_AREAS in results:
            outputs_to_move.append((results[self.OUTPUT_PLUVIAL_AREAS], "Pluvial Areas"))
        
        for layer_id, layer_type in outputs_to_move:
            layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
            if layer:
                from .helpers import move_layer_to_benefit_area_group
                success = move_layer_to_benefit_area_group(layer.id())
                if success:
                    feedback.pushInfo(f"{layer_type} layer moved to 'Benefit Area Analysis' group")
                else:
                    feedback.pushInfo(f"Could not move {layer_type} layer to group (layer created successfully)")
        
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
            QgsProcessingParameterEnum(
                self.OUTPUT_TYPE,
                'Output Type',
                options=['Boundary Lines', 'Area Polygons'],
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TIME_THRESHOLD,
                'Time Threshold (delta_t in hours)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=12.0,
                minValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_SEGMENT_LENGTH,
                'Minimum Segment Length (feet) - for boundary lines only',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=150.0,
                minValue=0.0,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.OVERRIDE_CRS,
                'Override CRS (Optional)',
                optional=True
            )
        )
        
        # Output for boundary lines
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                'Fluvial-Pluvial Boundary',
                QgsProcessing.TypeVectorLine,
                optional=True
            )
        )
        
        # Outputs for area polygons
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_FLUVIAL_AREAS,
                'Fluvial Areas',
                QgsProcessing.TypeVectorPolygon,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_PLUVIAL_AREAS,
                'Pluvial Areas',
                QgsProcessing.TypeVectorPolygon,
                optional=True
            )
        )

    def _get_mesh_data_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get mesh cell data and max water surface times.
        """
        all_data = []
        proj_wkt = None
        
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                from ras_commander import HdfBase, HdfUtils

                # Get projection
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Get start time
                start_time = HdfBase.get_simulation_start_time(hdf_file)

                # Get mesh area names
                flow_areas_path = "Geometry/2D Flow Areas"
                if flow_areas_path not in hdf_file:
                    return None, None, []
                
                attributes = hdf_file[f"{flow_areas_path}/Attributes"][()]
                mesh_names = [name.decode('utf-8') if isinstance(name, bytes) else str(name) 
                             for name in attributes["Name"]]

                # Process each mesh
                for mesh_name in mesh_names:
                    if feedback:
                        feedback.pushInfo(f"Processing mesh: {mesh_name}")
                    
                    # Get cell centers
                    centers_path = f"Geometry/2D Flow Areas/{mesh_name}/Cells Center Coordinate"
                    if centers_path not in hdf_file:
                        continue
                    cell_centers = hdf_file[centers_path][()]
                    
                    # Get maximum water surface data
                    summary_path = f"Results/Unsteady/Output/Output Blocks/Base Output/Summary Output/2D Flow Areas/{mesh_name}/Maximum Water Surface"
                    if summary_path not in hdf_file:
                        continue
                    
                    data = hdf_file[summary_path][:]
                    
                    # Data should be 2D array: [values, times]
                    if data.ndim != 2 or data.shape[0] != 2:
                        continue
                    
                    # Combine data
                    for cell_id, center_coords in enumerate(cell_centers):
                        if cell_id < data.shape[1]:
                            # Convert time from days to datetime
                            time_of_max = HdfUtils.convert_timesteps_to_datetimes(
                                np.array([data[1, cell_id]]), start_time, time_unit="days"
                            )[0]
                            
                            all_data.append({
                                'mesh_name': mesh_name,
                                'cell_id': cell_id,
                                'max_wse': float(data[0, cell_id]),
                                'max_wse_time': time_of_max,
                                'center_x': center_coords[0],
                                'center_y': center_coords[1]
                            })
                
                return proj_wkt, pd.DataFrame(all_data)
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading mesh data from HDF: {e}")

    def _get_mesh_cell_polygons_direct(self, hdf_path, feedback=None):
        """
        Direct HDF access to get mesh cell polygons.
        """
        from shapely.ops import polygonize
        
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                flow_areas_path = "Geometry/2D Flow Areas"
                if flow_areas_path not in hdf_file:
                    return {}
                
                attributes = hdf_file[f"{flow_areas_path}/Attributes"][()]
                mesh_names = [name.decode('utf-8') if isinstance(name, bytes) else str(name) 
                             for name in attributes["Name"]]
                
                all_cell_polygons = {}
                
                for mesh_name in mesh_names:
                    if feedback:
                        feedback.pushInfo(f"Loading cell polygons for mesh: {mesh_name}")
                    
                    # Read face data
                    facepoints_index = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces FacePoint Indexes"][()]
                    facepoints_coords = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/FacePoints Coordinate"][()]
                    faces_perim_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Info"][()]
                    faces_perim_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Faces Perimeter Values"][()]
                    
                    # Build face geometries
                    face_geoms = {}
                    for face_id, ((pnt_a_idx, pnt_b_idx), (start_row, count)) in enumerate(zip(facepoints_index, faces_perim_info)):
                        coords = [facepoints_coords[pnt_a_idx]]
                        if count > 0:
                            coords.extend(faces_perim_values[start_row:start_row + count])
                        coords.append(facepoints_coords[pnt_b_idx])
                        face_geoms[face_id] = LineString(coords)
                    
                    # Get cell face info
                    cell_face_info = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Cells Face and Orientation Info"][()]
                    cell_face_values = hdf_file[f"Geometry/2D Flow Areas/{mesh_name}/Cells Face and Orientation Values"][()][:, 0]
                    
                    # Build cell polygons
                    cell_polygons = {}
                    for cell_id, (start, length) in enumerate(cell_face_info[:, :2]):
                        face_ids = cell_face_values[start:start + length]
                        face_lines = [face_geoms[fid] for fid in face_ids if fid in face_geoms]
                        
                        if face_lines:
                            try:
                                polygons = list(polygonize(face_lines))
                                if polygons:
                                    cell_polygons[cell_id] = polygons[0]
                            except:
                                pass
                    
                    all_cell_polygons[mesh_name] = cell_polygons
                
                return all_cell_polygons
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading cell polygons from HDF: {e}")

    def _process_cell_adjacencies(self, cell_polygons_dict):
        """Process cell adjacencies by extracting shared edges."""
        cell_adjacency = defaultdict(list)
        common_edges = defaultdict(dict)
        
        # Flatten all cells with mesh name prefix
        all_cells = {}
        for mesh_name, cells in cell_polygons_dict.items():
            for cell_id, poly in cells.items():
                key = f"{mesh_name}_{cell_id}"
                all_cells[key] = poly
        
        # Build edge to cells mapping
        edge_to_cells = defaultdict(set)

        def edge_key(coords1, coords2, precision=8):
            coords1 = tuple(round(coord, precision) for coord in coords1)
            coords2 = tuple(round(coord, precision) for coord in coords2)
            return tuple(sorted([coords1, coords2]))

        # Extract edges from each polygon
        for cell_key, poly in all_cells.items():
            if poly.is_empty or not poly.is_valid:
                continue
            
            coords = list(poly.exterior.coords)
            num_coords = len(coords)
            for i in range(num_coords - 1):
                coord1 = coords[i]
                coord2 = coords[i + 1]
                key = edge_key(coord1, coord2)
                edge_to_cells[key].add(cell_key)

        # Process edge_to_cells to build adjacency
        for edge, cells in edge_to_cells.items():
            cells = list(cells)
            if len(cells) >= 2:
                for i in range(len(cells)):
                    for j in range(i + 1, len(cells)):
                        cell1 = cells[i]
                        cell2 = cells[j]
                        if cell2 not in cell_adjacency[cell1]:
                            cell_adjacency[cell1].append(cell2)
                        if cell1 not in cell_adjacency[cell2]:
                            cell_adjacency[cell2].append(cell1)
                        
                        common_edge = LineString([edge[0], edge[1]])
                        common_edges[cell1][cell2] = common_edge
                        common_edges[cell2][cell1] = common_edge

        return cell_adjacency, common_edges

    def _identify_boundary_edges(self, cell_adjacency, common_edges, cell_times, delta_t):
        """Identify boundary edges between cells with significant time differences."""
        valid_times = {k: v for k, v in cell_times.items() if pd.notna(v)}
        processed_pairs = set()
        boundary_edges = []

        for cell_id, neighbors in cell_adjacency.items():
            if cell_id not in valid_times:
                continue
                
            cell_time = valid_times[cell_id]

            for neighbor_id in neighbors:
                if neighbor_id not in valid_times:
                    continue
                    
                cell_pair = tuple(sorted([cell_id, neighbor_id]))
                if cell_pair in processed_pairs:
                    continue
                    
                neighbor_time = valid_times[neighbor_id]
                if pd.isna(cell_time) or pd.isna(neighbor_time):
                    continue
                
                time_diff = abs((cell_time - neighbor_time).total_seconds() / 3600)
                
                if time_diff >= delta_t:
                    boundary_edges.append(common_edges[cell_id][neighbor_id])
                
                processed_pairs.add(cell_pair)

        return boundary_edges

    def _classify_cells_by_flood_timing(self, cell_data_df, delta_t):
        """Classify cells as fluvial or pluvial based on flood arrival time."""
        # Find the earliest flood time
        valid_times = cell_data_df[cell_data_df['max_wse_time'].notna()]['max_wse_time']
        if valid_times.empty:
            return {}, {}
        
        earliest_time = valid_times.min()
        
        # Calculate hours from earliest flood
        cell_data_df['hours_from_start'] = (
            cell_data_df['max_wse_time'] - earliest_time
        ).dt.total_seconds() / 3600
        
        # Classify cells
        fluvial_cells = {}
        pluvial_cells = {}
        
        for mesh_name in cell_data_df['mesh_name'].unique():
            mesh_data = cell_data_df[cell_data_df['mesh_name'] == mesh_name]
            
            # Fluvial: flooded before delta_t
            fluvial_mask = mesh_data['hours_from_start'] < delta_t
            fluvial_ids = mesh_data[fluvial_mask]['cell_id'].tolist()
            if fluvial_ids:
                fluvial_cells[mesh_name] = fluvial_ids
            
            # Pluvial: flooded after delta_t
            pluvial_mask = mesh_data['hours_from_start'] >= delta_t
            pluvial_ids = mesh_data[pluvial_mask]['cell_id'].tolist()
            if pluvial_ids:
                pluvial_cells[mesh_name] = pluvial_ids
        
        return fluvial_cells, pluvial_cells

    def _group_contiguous_cells(self, cell_ids_by_mesh, cell_polygons_dict):
        """Group contiguous cells of the same type into areas."""
        contiguous_areas = []
        
        for mesh_name, cell_ids in cell_ids_by_mesh.items():
            if mesh_name not in cell_polygons_dict:
                continue
                
            mesh_polygons = cell_polygons_dict[mesh_name]
            
            # Get polygons for the specified cells
            cell_polys = []
            for cell_id in cell_ids:
                if cell_id in mesh_polygons:
                    cell_polys.append(mesh_polygons[cell_id])
            
            if not cell_polys:
                continue
            
            # Union all polygons and extract individual components
            try:
                merged = unary_union(cell_polys)
                
                # Extract individual polygons
                if isinstance(merged, Polygon):
                    contiguous_areas.append(merged)
                elif isinstance(merged, MultiPolygon):
                    contiguous_areas.extend(list(merged.geoms))
            except Exception as e:
                # If union fails, add individual polygons
                contiguous_areas.extend(cell_polys)
        
        return contiguous_areas

    def _filter_short_segments(self, line_segments, min_length_ft):
        """Filter out line segments shorter than the specified minimum length."""
        if not line_segments:
            return []
        
        filtered_segments = []
        for segment in line_segments:
            segment_length = segment.length
            if segment_length >= min_length_ft:
                filtered_segments.append(segment)
        
        return filtered_segments

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        output_type = self.parameterAsEnum(parameters, self.OUTPUT_TYPE, context)
        delta_t = self.parameterAsDouble(parameters, self.TIME_THRESHOLD, context)
        min_segment_length = self.parameterAsDouble(parameters, self.MIN_SEGMENT_LENGTH, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # Step 1: Get mesh cell data and maximum water surface times
            feedback.pushInfo("Loading mesh cell data and water surface times...")
            proj_wkt, cell_data_df = self._get_mesh_data_direct(hdf_path, feedback)
            
            if cell_data_df is None or cell_data_df.empty:
                raise QgsProcessingException("No mesh cell data found in the HDF file.")
            
            # Get cell polygons
            feedback.pushInfo("Loading mesh cell polygons...")
            cell_polygons_dict = self._get_mesh_cell_polygons_direct(hdf_path, feedback)
            
            if not cell_polygons_dict:
                raise QgsProcessingException("No mesh cell polygons found in the HDF file.")
            
        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed during initial data load: {e}")

        # Check for CRS
        if proj_wkt:
            feedback.pushInfo(f"CRS found in HEC-RAS project")
        elif override_crs and override_crs.isValid():
            proj_wkt = override_crs.toWkt()
            feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
        else:
            raise QgsProcessingException(
                "Coordinate Reference System (CRS) could not be determined. "
                "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                "or provide a valid Override CRS in the tool dialog."
            )

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        # Process based on output type
        if output_type == 0:  # Boundary Lines
            feedback.pushInfo("Generating fluvial-pluvial boundary lines...")
            
            # Process cell adjacencies
            cell_adjacency, common_edges = self._process_cell_adjacencies(cell_polygons_dict)
            
            # Create cell times lookup
            cell_times = {}
            for _, row in cell_data_df.iterrows():
                key = f"{row['mesh_name']}_{row['cell_id']}"
                cell_times[key] = row['max_wse_time']
            
            # Identify boundary edges
            boundary_edges = self._identify_boundary_edges(
                cell_adjacency, common_edges, cell_times, delta_t
            )
            
            if not boundary_edges:
                feedback.pushInfo("No boundary edges found with current threshold.")
                fields = QgsFields()
                (sink, dest_id) = self.parameterAsSink(
                    parameters, self.OUTPUT_LAYER, context, fields, 
                    QgsWkbTypes.LineString, qgis_crs
                )
                return {self.OUTPUT_LAYER: dest_id}
            
            # Filter short segments
            filtered_lines = self._filter_short_segments(boundary_edges, min_segment_length)
            
            if not filtered_lines:
                feedback.pushInfo("No segments remain after filtering.")
                fields = QgsFields()
                (sink, dest_id) = self.parameterAsSink(
                    parameters, self.OUTPUT_LAYER, context, fields, 
                    QgsWkbTypes.LineString, qgis_crs
                )
                return {self.OUTPUT_LAYER: dest_id}
            
            # Create output
            fields = QgsFields()
            fields.append(QgsField("boundary_type", QMetaType.Type.QString))
            
            (sink, dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_LAYER, context, fields,
                QgsWkbTypes.LineString, qgis_crs
            )
            
            if sink is None:
                raise QgsProcessingException("Could not create sink for output layer.")
            
            # Add features
            for line in filtered_lines:
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setGeometry(QgsGeometry.fromWkt(line.wkt))
                feature.setAttribute("boundary_type", "fluvial_pluvial_boundary")
                sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            feedback.pushInfo(f"Created {len(filtered_lines)} boundary line segments")
            return {self.OUTPUT_LAYER: dest_id}
            
        else:  # Area Polygons
            feedback.pushInfo("Generating fluvial and pluvial area polygons...")
            
            # Classify cells
            fluvial_cells, pluvial_cells = self._classify_cells_by_flood_timing(
                cell_data_df, delta_t
            )
            
            # Group contiguous cells
            feedback.pushInfo("Grouping contiguous fluvial areas...")
            fluvial_areas = self._group_contiguous_cells(fluvial_cells, cell_polygons_dict)
            
            feedback.pushInfo("Grouping contiguous pluvial areas...")
            pluvial_areas = self._group_contiguous_cells(pluvial_cells, cell_polygons_dict)
            
            # Create output fields
            fields = QgsFields()
            fields.append(QgsField("area_type", QMetaType.Type.QString))
            fields.append(QgsField("area_sqft", QMetaType.Type.Double))
            fields.append(QgsField("area_acres", QMetaType.Type.Double))
            
            # Create fluvial areas output
            (fluvial_sink, fluvial_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_FLUVIAL_AREAS, context, fields,
                QgsWkbTypes.Polygon, qgis_crs
            )
            
            # Create pluvial areas output
            (pluvial_sink, pluvial_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_PLUVIAL_AREAS, context, fields,
                QgsWkbTypes.Polygon, qgis_crs
            )
            
            if fluvial_sink is None or pluvial_sink is None:
                raise QgsProcessingException("Could not create sinks for output layers.")
            
            # Add fluvial features
            feedback.pushInfo(f"Writing {len(fluvial_areas)} fluvial area polygons...")
            for i, poly in enumerate(fluvial_areas):
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setGeometry(QgsGeometry.fromWkt(poly.wkt))
                feature.setAttribute("area_type", "fluvial")
                feature.setAttribute("area_sqft", poly.area)
                feature.setAttribute("area_acres", poly.area / 43560.0)
                fluvial_sink.addFeature(feature, QgsFeatureSink.FastInsert)
                
                if i % 100 == 0:
                    feedback.setProgress(int((i / len(fluvial_areas)) * 50))
            
            # Add pluvial features
            feedback.pushInfo(f"Writing {len(pluvial_areas)} pluvial area polygons...")
            for i, poly in enumerate(pluvial_areas):
                feature = QgsFeature()
                feature.setFields(fields)
                feature.setGeometry(QgsGeometry.fromWkt(poly.wkt))
                feature.setAttribute("area_type", "pluvial")
                feature.setAttribute("area_sqft", poly.area)
                feature.setAttribute("area_acres", poly.area / 43560.0)
                pluvial_sink.addFeature(feature, QgsFeatureSink.FastInsert)
                
                if i % 100 == 0:
                    feedback.setProgress(50 + int((i / len(pluvial_areas)) * 50))
            
            feedback.pushInfo(f"Successfully created fluvial ({len(fluvial_areas)}) and pluvial ({len(pluvial_areas)}) area polygons")
            
            return {
                self.OUTPUT_FLUVIAL_AREAS: fluvial_dest_id,
                self.OUTPUT_PLUVIAL_AREAS: pluvial_dest_id
            }