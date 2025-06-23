# ras_commander_qgis/processing/alg_load_2d_breaklines.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
import h5py
import numpy as np
from shapely.geometry import LineString, MultiLineString

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

class Load2DBreaklinesAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 2D breaklines from a HEC-RAS geometry HDF file.
    
    This tool extracts 2D mesh breakline geometry and attributes,
    and loads them as a line vector layer in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DBreaklinesAlgorithm()

    def name(self):
        return 'load_2d_breaklines'

    def displayName(self):
        return 'Load 2D Breaklines'

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
                    feedback.pushInfo(f"Breaklines layer moved to 'Benefit Area Analysis' group")
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
                '2D Breaklines',
                QgsProcessing.TypeVectorLine
            )
        )

    def _get_breaklines_direct(self, hdf_path):
        """
        Direct HDF access to get breaklines without CRS conflicts.
        
        This bypasses the ras-commander GeoDataFrame creation to avoid pyproj conflicts.
        """
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                # Get projection information first
                from ras_commander import HdfBase
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Check if breaklines exist
                breaklines_path = "Geometry/2D Flow Area Break Lines"
                if breaklines_path not in hdf_file:
                    return None, None, []
                
                bl_line_data = hdf_file[breaklines_path]
                attributes = bl_line_data["Attributes"][()]
                
                # Initialize lists to store breakline data
                valid_ids = []
                valid_names = []
                wkt_geometries = []  # Store WKT strings directly

                # Track invalid breaklines for summary
                zero_length_count = 0
                single_point_count = 0
                other_error_count = 0

                # Process each breakline
                for idx, (pnt_start, pnt_cnt, part_start, part_cnt) in enumerate(bl_line_data["Polyline Info"][()]):
                    # Decode name
                    name = attributes["Name"][idx]
                    if isinstance(name, bytes):
                        name = name.decode('utf-8')
                    else:
                        name = str(name)

                    # Check for zero-length breaklines
                    if pnt_cnt == 0:
                        zero_length_count += 1
                        continue

                    # Check for single-point breaklines
                    if pnt_cnt == 1:
                        single_point_count += 1
                        continue

                    try:
                        points = bl_line_data["Polyline Points"][()][pnt_start:pnt_start + pnt_cnt]
                        
                        # Additional validation of points array
                        if len(points) < 2:
                            single_point_count += 1
                            continue

                        if part_cnt == 1:
                            geom = LineString(points)
                        else:
                            parts = bl_line_data["Polyline Parts"][()][part_start:part_start + part_cnt]
                            line_parts = []
                            for part_pnt_start, part_pnt_cnt in parts:
                                if part_pnt_cnt > 1:  # Skip single-point parts
                                    part_points = points[part_pnt_start:part_pnt_start + part_pnt_cnt]
                                    line_parts.append(LineString(part_points))
                            
                            # Skip if no valid parts remain
                            if not line_parts:
                                other_error_count += 1
                                continue
                            
                            geom = MultiLineString(line_parts)

                        valid_ids.append(idx)
                        valid_names.append(name)
                        # Convert to WKT immediately - don't store geometry objects!
                        wkt_geometries.append(geom.wkt)

                    except Exception as e:
                        other_error_count += 1
                        continue

                # Log summary of invalid breaklines
                total_invalid = zero_length_count + single_point_count + other_error_count
                if total_invalid > 0:
                    pass  # Silent handling of invalid breaklines

                # Create raw data structure WITHOUT geometry column
                raw_data = {
                    'bl_id': valid_ids,
                    'Name': valid_names,
                }
                
                return proj_wkt, raw_data, wkt_geometries
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading breaklines directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Direct HDF Access to Bypass ras-commander CRS Issues ---
            feedback.pushInfo(f"Loading 2D breaklines from {hdf_path}...")
            
            proj_wkt, raw_data, wkt_geometries = self._get_breaklines_direct(hdf_path)
            
            if raw_data is None or len(wkt_geometries) == 0:
                raise QgsProcessingException("No 2D breaklines found in the HDF file.")
            
            # Create raw DataFrame (no geometry column yet)
            raw_df = pd.DataFrame(raw_data)
            
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
        fields.append(QgsField("bl_id", QMetaType.Type.Int))
        fields.append(QgsField("Name", QMetaType.Type.QString))

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
        feedback.pushInfo(f"Processing {total_features} 2D breaklines...")
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            
            # Set geometry
            try:
                feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            except Exception as e:
                feedback.pushInfo(f"Warning: Failed to set geometry for feature {i}: {e}")
                continue
            
            # Set attributes
            feature.setAttribute("bl_id", int(row['bl_id']))
            feature.setAttribute("Name", str(row['Name']))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 1000 == 0:  # Report progress more frequently
                progress = int((i / total_features) * 100)
                feedback.setProgress(progress)
                feedback.pushInfo(f"Processed {i+1} of {total_features} features...")
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully processed {total_features} 2D breaklines")
        return {self.OUTPUT_LAYER: dest_id}