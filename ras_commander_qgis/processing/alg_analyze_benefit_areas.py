# ras_commander_qgis/processing/alg_analyze_benefit_areas.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point, Polygon
from collections import defaultdict
import numpy as np

# Try to import STRtree from different possible locations
try:
    from shapely.strtree import STRtree
except ImportError:
    try:
        from shapely.spatial import STRtree
    except ImportError:
        # Fallback: no spatial indexing available
        STRtree = None

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
    QgsProject,
    QgsVectorLayer,
    QgsProcessingUtils)
from PyQt5.QtCore import QMetaType

class AnalyzeBenefitAreasAlgorithm(QgsProcessingAlgorithm):
    """
    Analyzes benefit areas by comparing maximum water surface elevations 
    between existing and proposed conditions HEC-RAS plans.
    
    This tool creates five output layers:
    - Net Benefit Areas: Contiguous polygons where WSE is reduced
    - Net Rise Areas: Contiguous polygons where WSE is increased  
    - Existing Conditions Max WSEL: Point layer of existing max WSE
    - Proposed Conditions Max WSEL: Point layer of proposed max WSE
    - Calculated Difference: Point layer showing WSE differences
    """
    EXISTING_HDF = 'EXISTING_HDF'
    PROPOSED_HDF = 'PROPOSED_HDF'
    MIN_DELTA = 'MIN_DELTA'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_BENEFIT_AREAS = 'OUTPUT_BENEFIT_AREAS'
    OUTPUT_RISE_AREAS = 'OUTPUT_RISE_AREAS'
    OUTPUT_EXISTING_POINTS = 'OUTPUT_EXISTING_POINTS'
    OUTPUT_PROPOSED_POINTS = 'OUTPUT_PROPOSED_POINTS'
    OUTPUT_DIFFERENCE_POINTS = 'OUTPUT_DIFFERENCE_POINTS'

    def createInstance(self):
        return AnalyzeBenefitAreasAlgorithm()

    def name(self):
        return 'analyze_benefit_areas'

    def displayName(self):
        return 'Analyze Benefit Areas'

    def group(self):
        return 'Analysis Algorithms'

    def groupId(self):
        return 'ras_analysis'

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        """Post-process to move all created layers to the Benefit Area Analysis group."""
        results = super().postProcessAlgorithm(context, feedback) or {}
        
        # List of all output parameters
        output_params = [
            self.OUTPUT_BENEFIT_AREAS,
            self.OUTPUT_RISE_AREAS,
            self.OUTPUT_EXISTING_POINTS,
            self.OUTPUT_PROPOSED_POINTS,
            self.OUTPUT_DIFFERENCE_POINTS
        ]
        
        # Import the helper function
        from .helpers import move_layer_to_benefit_area_group
        
        # Move each output layer to the Benefit Area Analysis group
        moved_count = 0
        for param_name in output_params:
            if param_name in results:
                layer_id = results[param_name]
                
                # For sinks, we need to get the actual layer
                layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
                if layer:
                    success = move_layer_to_benefit_area_group(layer.id())
                    if success:
                        moved_count += 1
        
        if moved_count > 0:
            feedback.pushInfo(f"Moved {moved_count} layers to 'Benefit Area Analysis' group")
        else:
            feedback.pushInfo("Could not move layers to group (layers created successfully)")
        
        return results

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.EXISTING_HDF,
                'Existing Conditions Plan HDF File',
                behavior=QgsProcessingParameterFile.File
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.PROPOSED_HDF,
                'Proposed Conditions Plan HDF File',
                behavior=QgsProcessingParameterFile.File
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_DELTA,
                'Minimum Delta Threshold (feet)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.1,
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
        
        # Polygon outputs
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_BENEFIT_AREAS,
                'Net Benefit Areas',
                QgsProcessing.TypeVectorPolygon
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_RISE_AREAS,
                'Net Rise Areas',
                QgsProcessing.TypeVectorPolygon
            )
        )
        
        # Point outputs
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_EXISTING_POINTS,
                'Existing Conditions Max WSEL',
                QgsProcessing.TypeVectorPoint
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_PROPOSED_POINTS,
                'Proposed Conditions Max WSEL',
                QgsProcessing.TypeVectorPoint
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_DIFFERENCE_POINTS,
                'Calculated Difference',
                QgsProcessing.TypeVectorPoint
            )
        )

    def _get_max_wse_points_safe(self, hdf_path, plan_name, feedback):
        """
        Safely get max WSE points using firewall pattern.
        
        Returns:
            tuple: (proj_wkt, crs_name, points_df, wkt_geometries)
        """
        try:
            from ras_commander import HdfResultsMesh
            feedback.pushInfo(f"Loading max WSE from {plan_name}: {hdf_path}")
            
            initial_gdf = HdfResultsMesh.get_mesh_max_ws(hdf_path)
            if initial_gdf is None or initial_gdf.empty:
                raise QgsProcessingException(f"No max WSE data found in {plan_name}")

            # --- FIREWALL ---
            # Deconstruct into primitives - CAPTURE CRS NAME IMMEDIATELY
            proj_wkt = initial_gdf.crs.to_wkt() if initial_gdf.crs else None
            crs_name = initial_gdf.crs.name if initial_gdf.crs else None
            wkt_geometries = initial_gdf.geometry.to_wkt()
            raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
            # ⚠️ NEVER reference initial_gdf after this point!
            
            return proj_wkt, crs_name, raw_df, wkt_geometries
            
        except Exception as e:
            raise QgsProcessingException(f"Failed to load {plan_name} max WSE data: {e}")

    def _get_mesh_cells_safe(self, hdf_path, feedback):
        """
        Safely get mesh cell polygons using firewall pattern.
        
        Returns:
            tuple: (cells_df, cell_wkt_geometries)
        """
        try:
            from ras_commander import HdfMesh
            feedback.pushInfo(f"Loading mesh cells from {hdf_path}")
            
            initial_gdf = HdfMesh.get_mesh_cell_polygons(hdf_path)
            if initial_gdf is None or initial_gdf.empty:
                raise QgsProcessingException("No mesh cells found")

            # --- FIREWALL ---
            wkt_geometries = initial_gdf.geometry.to_wkt()
            raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
            
            return raw_df, wkt_geometries
            
        except Exception as e:
            raise QgsProcessingException(f"Failed to load mesh cells: {e}")

    def _find_matching_points(self, existing_df, existing_geoms, proposed_df, proposed_geoms, feedback):
        """
        Find points with matching X,Y coordinates between existing and proposed plans.
        
        Returns:
            pandas.DataFrame: DataFrame with matched points and WSE differences
        """
        feedback.pushInfo("Finding matching points between plans...")
        
        # Create coordinate lookup for existing points
        existing_coords = {}
        for i, (_, row) in enumerate(existing_df.iterrows()):
            geom = loads(existing_geoms[i])
            coord_key = (round(geom.x, 6), round(geom.y, 6))  # Round to avoid floating point issues
            existing_coords[coord_key] = {
                'index': i,
                'cell_id': row['cell_id'],
                'mesh_name': row['mesh_name'],
                'existing_wse': row['maximum_water_surface'],
                'geometry': geom
            }
        
        # Find matches in proposed points
        matches = []
        for i, (_, row) in enumerate(proposed_df.iterrows()):
            geom = loads(proposed_geoms[i])
            coord_key = (round(geom.x, 6), round(geom.y, 6))
            
            if coord_key in existing_coords:
                existing_point = existing_coords[coord_key]
                proposed_wse = row['maximum_water_surface']
                
                # Calculate difference (Proposed - Existing)
                # Negative = benefit (WSE reduced)
                # Positive = adverse impact (WSE increased)
                wse_diff = proposed_wse - existing_point['existing_wse']
                
                matches.append({
                    'cell_id': existing_point['cell_id'],
                    'mesh_name': existing_point['mesh_name'],
                    'existing_wse': existing_point['existing_wse'],
                    'proposed_wse': proposed_wse,
                    'wse_difference': wse_diff,
                    'geometry': existing_point['geometry']
                })
        
        feedback.pushInfo(f"Found {len(matches)} matching points out of {len(existing_df)} existing points")
        
        if not matches:
            raise QgsProcessingException("No matching points found between the two plans")
        
        return pd.DataFrame(matches)

    def _apply_delta_threshold(self, matched_df, min_delta, feedback):
        """
        Apply minimum delta threshold and classify points.
        
        Returns:
            tuple: (benefit_points_df, adverse_points_df)
        """
        feedback.pushInfo(f"Applying minimum delta threshold of {min_delta} feet...")
        
        # Filter points that exceed the threshold
        significant_changes = matched_df[abs(matched_df['wse_difference']) >= min_delta].copy()
        
        if significant_changes.empty:
            feedback.pushInfo("No points exceed the minimum delta threshold")
            return pd.DataFrame(), pd.DataFrame()
        
        # Classify points
        benefit_points = significant_changes[significant_changes['wse_difference'] < 0].copy()
        adverse_points = significant_changes[significant_changes['wse_difference'] > 0].copy()
        
        feedback.pushInfo(f"Found {len(benefit_points)} benefit points and {len(adverse_points)} adverse impact points")
        
        return benefit_points, adverse_points

    def _associate_points_with_cells(self, points_df, cells_df, cell_wkt_geometries, feedback):
        """
        Associate points with their corresponding mesh cell polygons.
        
        Returns:
            list: List of cell_ids that contain the points
        """
        if points_df.empty:
            return []
        
        feedback.pushInfo("Associating points with mesh cells...")
        
        # Create cell polygons
        cell_polygons = [loads(wkt) for wkt in cell_wkt_geometries]
        associated_cells = set()
        
        if STRtree is not None:
            # Use spatial indexing if available
            try:
                cell_tree = STRtree(cell_polygons)
                
                for _, point_row in points_df.iterrows():
                    point_geom = point_row['geometry']
                    
                    # Find potentially intersecting cells
                    possible_matches = cell_tree.query(point_geom)
                    
                    # Check actual intersection
                    for i in possible_matches:
                        if cell_polygons[i].contains(point_geom):
                            cell_id = cells_df.iloc[i]['cell_id']
                            associated_cells.add(cell_id)
                            break
            except Exception as e:
                feedback.pushInfo(f"Warning: Spatial indexing failed, using fallback method: {e}")
                # Fall back to brute force method
                STRtree_available = False
            else:
                STRtree_available = True
        else:
            STRtree_available = False
        
        if not STRtree_available:
            # Fallback: brute force search (slower but reliable)
            feedback.pushInfo("Using fallback point-in-polygon method...")
            
            for _, point_row in points_df.iterrows():
                point_geom = point_row['geometry']
                
                # Check each cell polygon
                for i, cell_polygon in enumerate(cell_polygons):
                    try:
                        if cell_polygon.contains(point_geom):
                            cell_id = cells_df.iloc[i]['cell_id']
                            associated_cells.add(cell_id)
                            break
                    except Exception as e:
                        # Skip invalid geometries
                        continue
        
        feedback.pushInfo(f"Associated {len(associated_cells)} cells with points")
        return list(associated_cells)

    def _find_adjacent_cells(self, target_cell_ids, cells_df, cell_wkt_geometries, feedback):
        """
        Find adjacent cells using edge-based adjacency detection.
        
        Returns:
            dict: adjacency mapping {cell_id: [adjacent_cell_ids]}
        """
        feedback.pushInfo("Building cell adjacency relationships...")
        
        # Build mapping from cell_id to index
        cell_id_to_index = {row['cell_id']: i for i, (_, row) in enumerate(cells_df.iterrows())}
        target_indices = [cell_id_to_index[cid] for cid in target_cell_ids if cid in cell_id_to_index]
        
        if not target_indices:
            return {}
        
        # Build edge-to-cells mapping for target cells only
        edge_to_cells = defaultdict(set)
        
        def edge_key(coords1, coords2, precision=6):
            coords1 = tuple(round(coord, precision) for coord in coords1)
            coords2 = tuple(round(coord, precision) for coord in coords2)
            return tuple(sorted([coords1, coords2]))
        
        for idx in target_indices:
            cell_geom = loads(cell_wkt_geometries[idx])
            cell_id = cells_df.iloc[idx]['cell_id']
            
            if cell_geom.is_empty or not cell_geom.is_valid:
                continue
            
            # Extract edges from polygon exterior
            coords = list(cell_geom.exterior.coords)
            for i in range(len(coords) - 1):
                edge = edge_key(coords[i], coords[i + 1])
                edge_to_cells[edge].add(cell_id)
        
        # Build adjacency mapping
        adjacency = defaultdict(set)
        for edge, cells in edge_to_cells.items():
            if len(cells) >= 2:
                cells_list = list(cells)
                for i in range(len(cells_list)):
                    for j in range(i + 1, len(cells_list)):
                        cell1, cell2 = cells_list[i], cells_list[j]
                        adjacency[cell1].add(cell2)
                        adjacency[cell2].add(cell1)
        
        # Convert sets to lists
        adjacency_dict = {k: list(v) for k, v in adjacency.items()}
        
        feedback.pushInfo(f"Built adjacency for {len(adjacency_dict)} cells")
        return adjacency_dict

    def _create_point_layers(self, existing_df, existing_geoms, proposed_df, proposed_geoms, 
                            matched_df, proj_wkt, parameters, context, feedback):
        """
        Create the three point output layers.
        
        Returns:
            tuple: (existing_dest_id, proposed_dest_id, difference_dest_id)
        """
        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)
        
        # 1. Existing Conditions Points
        existing_fields = QgsFields()
        existing_fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        existing_fields.append(QgsField("cell_id", QMetaType.Type.Int))
        existing_fields.append(QgsField("max_wse", QMetaType.Type.Double))
        
        (existing_sink, existing_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_EXISTING_POINTS, context, existing_fields,
            QgsWkbTypes.Point, qgis_crs
        )
        
        if existing_sink is None:
            raise QgsProcessingException("Could not create sink for existing conditions points.")
        
        feedback.pushInfo("Creating existing conditions points...")
        for i, (_, row) in enumerate(existing_df.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(existing_fields)
            geom = loads(existing_geoms[i])
            feature.setGeometry(QgsGeometry.fromWkt(geom.wkt))
            feature.setAttribute("mesh_name", row['mesh_name'])
            feature.setAttribute("cell_id", int(row['cell_id']))
            feature.setAttribute("max_wse", float(row['maximum_water_surface']))
            
            existing_sink.addFeature(feature, QgsFeatureSink.FastInsert)
        
        # 2. Proposed Conditions Points
        proposed_fields = QgsFields()
        proposed_fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        proposed_fields.append(QgsField("cell_id", QMetaType.Type.Int))
        proposed_fields.append(QgsField("max_wse", QMetaType.Type.Double))
        
        (proposed_sink, proposed_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_PROPOSED_POINTS, context, proposed_fields,
            QgsWkbTypes.Point, qgis_crs
        )
        
        if proposed_sink is None:
            raise QgsProcessingException("Could not create sink for proposed conditions points.")
        
        feedback.pushInfo("Creating proposed conditions points...")
        for i, (_, row) in enumerate(proposed_df.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(proposed_fields)
            geom = loads(proposed_geoms[i])
            feature.setGeometry(QgsGeometry.fromWkt(geom.wkt))
            feature.setAttribute("mesh_name", row['mesh_name'])
            feature.setAttribute("cell_id", int(row['cell_id']))
            feature.setAttribute("max_wse", float(row['maximum_water_surface']))
            
            proposed_sink.addFeature(feature, QgsFeatureSink.FastInsert)
        
        # 3. Difference Points (only matched points)
        difference_fields = QgsFields()
        difference_fields.append(QgsField("mesh_name", QMetaType.Type.QString))
        difference_fields.append(QgsField("cell_id", QMetaType.Type.Int))
        difference_fields.append(QgsField("existing_wse", QMetaType.Type.Double))
        difference_fields.append(QgsField("proposed_wse", QMetaType.Type.Double))
        difference_fields.append(QgsField("wse_difference", QMetaType.Type.Double))
        difference_fields.append(QgsField("change_type", QMetaType.Type.QString))
        
        (difference_sink, difference_dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_DIFFERENCE_POINTS, context, difference_fields,
            QgsWkbTypes.Point, qgis_crs
        )
        
        if difference_sink is None:
            raise QgsProcessingException("Could not create sink for difference points.")
        
        feedback.pushInfo("Creating difference points...")
        for i, (_, row) in enumerate(matched_df.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(difference_fields)
            feature.setGeometry(QgsGeometry.fromWkt(row['geometry'].wkt))
            feature.setAttribute("mesh_name", row['mesh_name'])
            feature.setAttribute("cell_id", int(row['cell_id']))
            feature.setAttribute("existing_wse", float(row['existing_wse']))
            feature.setAttribute("proposed_wse", float(row['proposed_wse']))
            feature.setAttribute("wse_difference", float(row['wse_difference']))
            
            # Classify change type
            if row['wse_difference'] < 0:
                change_type = "Benefit (WSE Reduced)"
            elif row['wse_difference'] > 0:
                change_type = "Rise (WSE Increased)"
            else:
                change_type = "No Change"
            
            feature.setAttribute("change_type", change_type)
            
            difference_sink.addFeature(feature, QgsFeatureSink.FastInsert)
        
        return existing_dest_id, proposed_dest_id, difference_dest_id

    def _group_contiguous_areas(self, cell_ids, adjacency, feedback):
            """
            Group adjacent cells into contiguous areas using flood-fill algorithm.
            
            Returns:
                list: List of contiguous area groups (each group is a list of cell_ids)
            """
            if not cell_ids:
                return []
            
            feedback.pushInfo("Grouping cells into contiguous areas...")
            
            unvisited = set(cell_ids)
            contiguous_groups = []
            
            while unvisited:
                # Start a new group with an unvisited cell
                start_cell = unvisited.pop()
                current_group = [start_cell]
                queue = [start_cell]
                
                # Flood-fill to find all connected cells
                while queue:
                    current_cell = queue.pop(0)
                    
                    # Check all adjacent cells
                    for neighbor in adjacency.get(current_cell, []):
                        if neighbor in unvisited:
                            unvisited.remove(neighbor)
                            current_group.append(neighbor)
                            queue.append(neighbor)
                
                contiguous_groups.append(current_group)
            
            feedback.pushInfo(f"Created {len(contiguous_groups)} contiguous area groups")
            return contiguous_groups


    def _create_contiguous_area_polygons(self, cell_groups, area_type, cells_df, cell_wkt_geometries, feedback):
        """
        Create polygon features for contiguous areas.
        
        Returns:
            list: List of feature dictionaries
        """
        features = []
        cell_id_to_index = {row['cell_id']: i for i, (_, row) in enumerate(cells_df.iterrows())}
        
        for group_idx, cell_group in enumerate(cell_groups):
            # Get polygons for this group
            group_polygons = []
            for cell_id in cell_group:
                if cell_id in cell_id_to_index:
                    idx = cell_id_to_index[cell_id]
                    poly_geom = loads(cell_wkt_geometries[idx])
                    if poly_geom.is_valid:
                        group_polygons.append(poly_geom)
            
            if group_polygons:
                # Union all polygons in the group
                merged_polygon = None
                try:
                    from shapely.ops import unary_union
                    merged_polygon = unary_union(group_polygons)
                except ImportError:
                    # Fallback: use iterative union for older shapely versions
                    try:
                        merged_polygon = group_polygons[0]
                        for poly in group_polygons[1:]:
                            merged_polygon = merged_polygon.union(poly)
                    except Exception as e:
                        feedback.pushInfo(f"Warning: Iterative union failed for {area_type} group {group_idx + 1}: {e}")
                except Exception as e:
                    feedback.pushInfo(f"Warning: Could not merge polygons for {area_type} group {group_idx + 1}: {e}")
                
                if merged_polygon is not None and merged_polygon.is_valid:
                    # Calculate area in square feet (assuming coordinates are in feet)
                    area_sqft = merged_polygon.area
                    
                    features.append({
                        'geometry': merged_polygon,
                        'area_type': area_type,
                        'group_id': group_idx + 1,
                        'cell_count': len(cell_group),
                        'area_sqft': area_sqft,
                        'area_acres': area_sqft / 43560.0  # Convert to acres
                    })
        
        return features

    def processAlgorithm(self, parameters, context, feedback):
        existing_hdf = self.parameterAsFile(parameters, self.EXISTING_HDF, context)
        proposed_hdf = self.parameterAsFile(parameters, self.PROPOSED_HDF, context)
        min_delta = self.parameterAsDouble(parameters, self.MIN_DELTA, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        # Step 1: Load max WSE data from both plans using firewall pattern
        try:
            existing_proj_wkt, existing_crs_name, existing_df, existing_geoms = self._get_max_wse_points_safe(
                existing_hdf, "Existing Conditions", feedback
            )
            
            proposed_proj_wkt, proposed_crs_name, proposed_df, proposed_geoms = self._get_max_wse_points_safe(
                proposed_hdf, "Proposed Conditions", feedback
            )
            
            # Use CRS from existing plan or override
            proj_wkt = existing_proj_wkt
            crs_name = existing_crs_name
            
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
            # Step 2: Find matching points and calculate differences
            matched_df = self._find_matching_points(
                existing_df, existing_geoms, proposed_df, proposed_geoms, feedback
            )
            
            # Step 3: Create point layers first
            existing_dest_id, proposed_dest_id, difference_dest_id = self._create_point_layers(
                existing_df, existing_geoms, proposed_df, proposed_geoms, 
                matched_df, proj_wkt, parameters, context, feedback
            )
            
            # Step 4: Apply delta threshold and classify points
            benefit_points, adverse_points = self._apply_delta_threshold(matched_df, min_delta, feedback)
            
            # Step 5: Load mesh cells from existing conditions plan
            cells_df, cell_wkt_geometries = self._get_mesh_cells_safe(existing_hdf, feedback)
            
            # Step 6: Create polygon layers for benefit and rise areas
            qgis_crs = QgsCoordinateReferenceSystem()
            qgis_crs.createFromWkt(proj_wkt)
            
            # Define fields for polygon layers
            polygon_fields = QgsFields()
            polygon_fields.append(QgsField("group_id", QMetaType.Type.Int))
            polygon_fields.append(QgsField("cell_count", QMetaType.Type.Int))
            polygon_fields.append(QgsField("area_sqft", QMetaType.Type.Double))
            polygon_fields.append(QgsField("area_acres", QMetaType.Type.Double))
            
            # Create benefit areas sink
            (benefit_sink, benefit_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_BENEFIT_AREAS, context, polygon_fields,
                QgsWkbTypes.Polygon, qgis_crs
            )
            
            # Create rise areas sink  
            (rise_sink, rise_dest_id) = self.parameterAsSink(
                parameters, self.OUTPUT_RISE_AREAS, context, polygon_fields,
                QgsWkbTypes.Polygon, qgis_crs
            )
            
            if benefit_sink is None or rise_sink is None:
                raise QgsProcessingException("Could not create sinks for polygon output layers.")
            
            # Process benefit areas
            if not benefit_points.empty:
                benefit_cell_ids = self._associate_points_with_cells(
                    benefit_points, cells_df, cell_wkt_geometries, feedback
                )
                if benefit_cell_ids:
                    benefit_adjacency = self._find_adjacent_cells(
                        benefit_cell_ids, cells_df, cell_wkt_geometries, feedback
                    )
                    benefit_groups = self._group_contiguous_areas(benefit_cell_ids, benefit_adjacency, feedback)
                    benefit_features = self._create_contiguous_area_polygons(
                        benefit_groups, "Benefit Area", cells_df, cell_wkt_geometries, feedback
                    )
                    
                    # Add benefit features to sink
                    for i, feature_data in enumerate(benefit_features):
                        if feedback.isCanceled():
                            break
                        
                        feature = QgsFeature()
                        feature.setFields(polygon_fields)
                        feature.setGeometry(QgsGeometry.fromWkt(feature_data['geometry'].wkt))
                        feature.setAttribute("group_id", feature_data['group_id'])
                        feature.setAttribute("cell_count", feature_data['cell_count'])
                        feature.setAttribute("area_sqft", feature_data['area_sqft'])
                        feature.setAttribute("area_acres", feature_data['area_acres'])
                        
                        benefit_sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            # Process rise areas
            if not adverse_points.empty:
                adverse_cell_ids = self._associate_points_with_cells(
                    adverse_points, cells_df, cell_wkt_geometries, feedback
                )
                if adverse_cell_ids:
                    adverse_adjacency = self._find_adjacent_cells(
                        adverse_cell_ids, cells_df, cell_wkt_geometries, feedback
                    )
                    adverse_groups = self._group_contiguous_areas(adverse_cell_ids, adverse_adjacency, feedback)
                    adverse_features = self._create_contiguous_area_polygons(
                        adverse_groups, "Rise Area", cells_df, cell_wkt_geometries, feedback
                    )
                    
                    # Add rise features to sink
                    for i, feature_data in enumerate(adverse_features):
                        if feedback.isCanceled():
                            break
                        
                        feature = QgsFeature()
                        feature.setFields(polygon_fields)
                        feature.setGeometry(QgsGeometry.fromWkt(feature_data['geometry'].wkt))
                        feature.setAttribute("group_id", feature_data['group_id'])
                        feature.setAttribute("cell_count", feature_data['cell_count'])
                        feature.setAttribute("area_sqft", feature_data['area_sqft'])
                        feature.setAttribute("area_acres", feature_data['area_acres'])
                        
                        rise_sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
        except Exception as e:
            raise QgsProcessingException(f"Failed during benefit area analysis: {e}")

        if feedback.isCanceled():
            return {}

        feedback.pushInfo("Analysis completed successfully")
        feedback.pushInfo("Created 5 output layers:")
        feedback.pushInfo("- Net Benefit Areas (polygons)")
        feedback.pushInfo("- Net Rise Areas (polygons)")  
        feedback.pushInfo("- Existing Conditions Max WSEL (points)")
        feedback.pushInfo("- Proposed Conditions Max WSEL (points)")
        feedback.pushInfo("- Calculated Difference (points)")
        
        # Return all output layer IDs
        return {
            self.OUTPUT_EXISTING_POINTS: existing_dest_id,
            self.OUTPUT_PROPOSED_POINTS: proposed_dest_id,
            self.OUTPUT_DIFFERENCE_POINTS: difference_dest_id,
            self.OUTPUT_BENEFIT_AREAS: benefit_dest_id,
            self.OUTPUT_RISE_AREAS: rise_dest_id
        }






