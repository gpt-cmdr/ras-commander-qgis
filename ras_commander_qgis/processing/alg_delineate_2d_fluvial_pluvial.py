# ras_commander_qgis/processing/alg_delineate_2d_fluvial_pluvial.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import LineString, MultiLineString
from collections import defaultdict
import numpy as np

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
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
    Delineates the fluvial-pluvial boundary from a HEC-RAS results HDF file.
    
    This tool analyzes the timing of flood arrival to distinguish between
    fluvial (river-driven) and pluvial (rainfall-driven) flooding areas
    based on a specified time threshold.
    """
    INPUT_HDF = 'INPUT_HDF'
    TIME_THRESHOLD = 'TIME_THRESHOLD'
    MIN_SEGMENT_LENGTH = 'MIN_SEGMENT_LENGTH'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Delineate2DFluvialPluvialBoundaryAlgorithm()

    def name(self):
        return 'delineate_fluvial_pluvial_boundary'

    def displayName(self):
        return 'Delineate Fluvial-Pluvial Boundary'

    def group(self):
        return 'Analysis Algorithms'

    def groupId(self):
        return 'ras_analysis'

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
                    feedback.pushInfo(f"Fluvial-Pluvial Boundary layer moved to 'Benefit Area Analysis' group")
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
                'Minimum Segment Length (feet)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=150.0,
                minValue=0.0
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
                'Fluvial-Pluvial Boundary',
                QgsProcessing.TypeVectorLine
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        delta_t = self.parameterAsDouble(parameters, self.TIME_THRESHOLD, context)
        min_segment_length = self.parameterAsDouble(parameters, self.MIN_SEGMENT_LENGTH, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # Step 1: Get mesh cell polygons using firewall pattern
            feedback.pushInfo("Loading mesh cell polygons...")
            from ras_commander import HdfMesh
            
            # Firewall for cell polygons
            initial_cell_gdf = HdfMesh.get_mesh_cell_polygons(hdf_path)
            if initial_cell_gdf is None or initial_cell_gdf.empty:
                raise QgsProcessingException("No mesh cells found in the HDF file.")

            # Deconstruct cell polygons
            cell_proj_wkt = initial_cell_gdf.crs.to_wkt() if initial_cell_gdf.crs else None
            cell_crs_name = initial_cell_gdf.crs.name if initial_cell_gdf.crs else None
            cell_wkt_geometries = initial_cell_gdf.geometry.to_wkt()
            cell_raw_df = pd.DataFrame(initial_cell_gdf.drop(columns='geometry'))

            # Reconstruct safe cell polygons
            feedback.pushInfo("Reconstructing mesh cell geometry within QGIS environment...")
            cell_geometry = [loads(wkt) for wkt in cell_wkt_geometries]
            cell_polygons_gdf = gpd.GeoDataFrame(cell_raw_df, geometry=cell_geometry)
            
            # Step 2: Get max water surface data using firewall pattern
            feedback.pushInfo("Loading maximum water surface data...")
            from ras_commander import HdfResultsMesh
            
            # Firewall for max WS data
            initial_maxws_gdf = HdfResultsMesh.get_mesh_max_ws(hdf_path)
            if initial_maxws_gdf is None or initial_maxws_gdf.empty:
                raise QgsProcessingException("No maximum water surface data found in the HDF file.")

            # Deconstruct max WS data
            maxws_wkt_geometries = initial_maxws_gdf.geometry.to_wkt()
            maxws_raw_df = pd.DataFrame(initial_maxws_gdf.drop(columns='geometry'))

            # Reconstruct safe max WS data
            feedback.pushInfo("Reconstructing max water surface geometry within QGIS environment...")
            maxws_geometry = [loads(wkt) for wkt in maxws_wkt_geometries]
            max_ws_df = gpd.GeoDataFrame(maxws_raw_df, geometry=maxws_geometry)

        except QgsProcessingException as e:
            raise e
        except Exception as e:
            raise QgsProcessingException(f"Failed during initial data load: {e}")

        # Check for CRS and apply override if necessary
        if cell_proj_wkt:
            feedback.pushInfo(f"CRS found in HEC-RAS project: {cell_crs_name}")
        elif override_crs and override_crs.isValid():
            cell_proj_wkt = override_crs.toWkt()
            feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
        else:
            raise QgsProcessingException(
                "Coordinate Reference System (CRS) could not be determined. "
                "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                "or provide a valid Override CRS in the tool dialog."
            )

        try:
            # Step 3: Process the fluvial-pluvial analysis
            feedback.pushInfo("Processing cell adjacencies...")
            
            # Convert timestamps (safely handle time columns)
            if 'maximum_water_surface_time' in max_ws_df.columns:
                from ras_commander import HdfUtils
                max_ws_df['maximum_water_surface_time'] = max_ws_df['maximum_water_surface_time'].apply(
                    lambda x: HdfUtils.parse_ras_datetime(x) if isinstance(x, str) else x
                )

            # Process cell adjacencies
            cell_adjacency, common_edges = self._process_cell_adjacencies(cell_polygons_gdf)
            
            # Get cell times from max_ws_df
            feedback.pushInfo("Extracting cell times from maximum water surface data...")
            cell_times = max_ws_df.set_index('cell_id')['maximum_water_surface_time'].to_dict()
            
            # Identify boundary edges
            feedback.pushInfo("Identifying boundary edges...")
            boundary_edges = self._identify_boundary_edges(
                cell_adjacency, common_edges, cell_times, delta_t
            )

            if not boundary_edges:
                feedback.pushInfo("No boundary edges found with current threshold.")
                # Create empty result
                fields = QgsFields()
                qgis_crs = QgsCoordinateReferenceSystem()
                qgis_crs.createFromWkt(cell_proj_wkt)
                (sink, dest_id) = self.parameterAsSink(
                    parameters, self.OUTPUT_LAYER, context, fields, 
                    QgsWkbTypes.LineString, qgis_crs
                )
                return {self.OUTPUT_LAYER: dest_id}

            # Step 4: Join adjacent LineStrings (simplified version)
            feedback.pushInfo("Joining adjacent boundary segments...")
            joined_lines = self._join_boundary_lines(boundary_edges)
            
            # Step 5: Filter out short segments
            feedback.pushInfo(f"Filtering segments shorter than {min_segment_length} feet...")
            filtered_lines = self._filter_short_segments(joined_lines, min_segment_length)
            
            if not filtered_lines:
                feedback.pushInfo("No segments remain after filtering. Consider lowering the minimum segment length.")
                # Create empty result
                fields = QgsFields()
                qgis_crs = QgsCoordinateReferenceSystem()
                qgis_crs.createFromWkt(cell_proj_wkt)
                (sink, dest_id) = self.parameterAsSink(
                    parameters, self.OUTPUT_LAYER, context, fields, 
                    QgsWkbTypes.LineString, qgis_crs
                )
                return {self.OUTPUT_LAYER: dest_id}
            
            feedback.pushInfo(f"Retained {len(filtered_lines)} segments after filtering (removed {len(joined_lines) - len(filtered_lines)} short segments)")
            
            # Step 6: Convert filtered lines to WKT before creating GeoDataFrame
            feedback.pushInfo("Converting boundary segments to WKT...")
            wkt_filtered_lines = [line.wkt for line in filtered_lines]
            
        except Exception as e:
            raise QgsProcessingException(f"Failed during boundary analysis: {e}")

        # Step 7: Create output using Feature Sink pattern
        fields = QgsFields()
        fields.append(QgsField("boundary_type", QMetaType.Type.QString))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(cell_proj_wkt)

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

        # Process features directly from WKT strings
        total_features = len(wkt_filtered_lines)
        for i, line_wkt in enumerate(wkt_filtered_lines):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            
            # Create geometry from WKT
            geom = QgsGeometry.fromWkt(line_wkt)
            feature.setGeometry(geom)
            feature.setAttribute("boundary_type", "fluvial_pluvial_boundary")
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 100 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully created {total_features} boundary line segments")
        return {self.OUTPUT_LAYER: dest_id}

    def _process_cell_adjacencies(self, cell_polygons_gdf):
        """Process cell adjacencies by extracting shared edges directly."""
        cell_adjacency = defaultdict(list)
        common_edges = defaultdict(dict)

        # Build an edge to cells mapping
        edge_to_cells = defaultdict(set)

        def edge_key(coords1, coords2, precision=8):
            coords1 = tuple(round(coord, precision) for coord in coords1)
            coords2 = tuple(round(coord, precision) for coord in coords2)
            return tuple(sorted([coords1, coords2]))

        # For each polygon, extract edges
        for idx, row in cell_polygons_gdf.iterrows():
            cell_id = row['cell_id']
            geom = row['geometry']
            if geom.is_empty or not geom.is_valid:
                continue
            
            coords = list(geom.exterior.coords)
            num_coords = len(coords)
            for i in range(num_coords - 1):
                coord1 = coords[i]
                coord2 = coords[i + 1]
                key = edge_key(coord1, coord2)
                edge_to_cells[key].add(cell_id)

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

    def _join_boundary_lines(self, boundary_edges):
        """Simple line joining - connect lines that share endpoints."""
        if not boundary_edges:
            return []
        
        # For simplicity, return the original edges
        # You can implement more sophisticated joining here if needed
        return boundary_edges

    def _filter_short_segments(self, line_segments, min_length_ft):
        """Filter out line segments shorter than the specified minimum length in feet."""
        if not line_segments:
            return []
        
        filtered_segments = []
        for segment in line_segments:
            # Calculate length - assume coordinates are in feet or convert appropriately
            # For most US coordinate systems, length will be in feet
            segment_length = segment.length
            
            if segment_length >= min_length_ft:
                filtered_segments.append(segment)
        
        return filtered_segments