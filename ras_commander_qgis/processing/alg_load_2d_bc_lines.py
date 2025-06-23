# ras_commander_qgis/processing/alg_load_2d_bc_lines.py
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
    QgsProcessingUtils)
from PyQt5.QtCore import QMetaType

class Load2DBoundaryConditionLinesAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 2D boundary condition lines from a HEC-RAS geometry HDF file.
    
    This tool extracts 2D mesh boundary condition line geometry and attributes,
    and loads them as a line vector layer in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DBoundaryConditionLinesAlgorithm()

    def name(self):
        return 'load_2d_boundary_condition_lines'

    def displayName(self):
        return 'Load 2D Boundary Condition Lines'

    def group(self):
        return '2D Geometry Layers'

    def groupId(self):
        return 'ras_2d_geometry'

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
                    feedback.pushInfo(f"Boundary Condition Lines layer moved to 'Benefit Area Analysis' group")
                else:
                    feedback.pushInfo("Could not move layer to group (layer created successfully)")
        
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
                'Boundary Condition Lines',
                QgsProcessing.TypeVectorLine
            )
        )

    def _get_bc_lines_direct(self, hdf_path):
        """
        Direct HDF access to get boundary condition lines without CRS conflicts.
        
        This bypasses the ras-commander GeoDataFrame creation to avoid pyproj conflicts.
        """
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                # Get projection information first
                from ras_commander import HdfBase
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Check if boundary condition lines exist
                bc_lines_path = "Geometry/Boundary Condition Lines"
                if bc_lines_path not in hdf_file:
                    return None, None, []
                
                # Get boundary condition line names and types
                bc_attrs = hdf_file[f"{bc_lines_path}/Attributes"][()]
                bc_names = [name.decode('utf-8') if isinstance(name, bytes) else str(name) 
                           for name in bc_attrs["Name"]]
                bc_types = [typename.decode('utf-8') if isinstance(typename, bytes) else str(typename) 
                           for typename in bc_attrs["Type"]]
                
                # Get polyline geometry data
                polyline_info = hdf_file[f"{bc_lines_path}/Polyline Info"][()]
                polyline_parts = hdf_file[f"{bc_lines_path}/Polyline Parts"][()]
                polyline_points = hdf_file[f"{bc_lines_path}/Polyline Points"][()]
                
                # Create WKT strings directly - DO NOT create geometry objects!
                wkt_geometries = []
                for pnt_start, pnt_cnt, part_start, part_cnt in polyline_info:
                    points = polyline_points[pnt_start : pnt_start + pnt_cnt]
                    if part_cnt == 1:
                        # Convert directly to WKT string
                        line_wkt = LineString(points).wkt
                        wkt_geometries.append(line_wkt)
                    else:
                        # Handle multi-part lines
                        parts = polyline_parts[part_start : part_start + part_cnt]
                        line_parts = []
                        for part_pnt_start, part_pnt_cnt in parts:
                            part_points = points[part_pnt_start : part_pnt_start + part_pnt_cnt]
                            line_parts.append(LineString(part_points))
                        # For now, just use the first part and convert to WKT immediately
                        line_wkt = line_parts[0].wkt if line_parts else LineString([]).wkt
                        wkt_geometries.append(line_wkt)
                
                # Create raw data structure WITHOUT geometry column
                raw_data = {
                    'Name': bc_names,
                    'Type': bc_types,
                }
                
                return proj_wkt, raw_data, wkt_geometries
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading boundary condition lines directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Direct HDF Access to Bypass ras-commander CRS Issues ---
            feedback.pushInfo(f"Loading boundary condition lines from {hdf_path}...")
            
            proj_wkt, raw_data, wkt_geometries = self._get_bc_lines_direct(hdf_path)
            
            if raw_data is None or len(raw_data.get('Name', [])) == 0:
                raise QgsProcessingException("No boundary condition lines found in the HDF file.")
            
            # Create raw DataFrame (no geometry column yet)
            raw_df = pd.DataFrame({
                'Name': raw_data['Name'],
                'Type': raw_data['Type']
            })
            
            # Don't try to parse the CRS name - just report if we found one
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

        # Proceed with Feature Sink pattern using the safe GeoDataFrame
        fields = QgsFields()
        fields.append(QgsField("Name", QMetaType.Type.QString))
        fields.append(QgsField("Type", QMetaType.Type.QString))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

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

        total_features = len(gdf)
        feedback.pushInfo(f"Processing {total_features} boundary condition lines...")
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            # Set attributes for all defined fields
            for field in fields:
                col_name = field.name()
                if col_name in row and pd.notna(row[col_name]):
                    feature.setAttribute(col_name, str(row[col_name]))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 500 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully processed {total_features} boundary condition lines")
        return {self.OUTPUT_LAYER: dest_id}