# ras_commander_qgis/processing/alg_load_2d_mesh_area_perimeters.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
import h5py
import numpy as np
from shapely.geometry import Polygon

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

class Load2DMeshAreaPerimetersAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 2D mesh area perimeters from a HEC-RAS geometry HDF file.
    
    This tool extracts the 2D mesh area boundary polygons and their
    attributes, and loads them as a polygon vector layer in the "Benefit Area Analysis" group in QGIS.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load2DMeshAreaPerimetersAlgorithm()

    def name(self):
        return 'load_2d_mesh_area_perimeters'

    def displayName(self):
        return 'Load 2D Mesh Area Perimeters'

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
                    feedback.pushInfo(f"Mesh Area Perimeters layer moved to 'Benefit Area Analysis' group")
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
                'Mesh Area Perimeters',
                QgsProcessing.TypeVectorPolygon
            )
        )

    def _get_mesh_areas_direct(self, hdf_path):
        """
        Direct HDF access to get mesh area perimeters without CRS conflicts.
        
        This bypasses the ras-commander GeoDataFrame creation to avoid pyproj conflicts.
        """
        try:
            with h5py.File(hdf_path, 'r') as hdf_file:
                # Get projection information first
                from ras_commander import HdfBase
                proj_wkt = HdfBase.get_projection(hdf_path)
                
                # Check if 2D Flow Areas exist
                flow_areas_path = "Geometry/2D Flow Areas"
                if flow_areas_path not in hdf_file:
                    return None, None, []
                
                # Get mesh area names
                attributes_path = f"{flow_areas_path}/Attributes"
                if attributes_path not in hdf_file:
                    return None, None, []
                
                # Decode mesh area names safely
                attributes = hdf_file[attributes_path][()]
                mesh_area_names = []
                for name in attributes["Name"]:
                    if isinstance(name, bytes):
                        mesh_area_names.append(name.decode('utf-8'))
                    else:
                        mesh_area_names.append(str(name))
                
                if not mesh_area_names:
                    return None, None, []
                
                # Get perimeter WKT strings for each mesh area
                wkt_geometries = []
                for mesh_name in mesh_area_names:
                    perimeter_path = f"{flow_areas_path}/{mesh_name}/Perimeter"
                    if perimeter_path in hdf_file:
                        perimeter_coords = hdf_file[perimeter_path][()]
                        # Convert directly to WKT string - DO NOT create geometry object!
                        polygon_wkt = Polygon(perimeter_coords).wkt
                        wkt_geometries.append(polygon_wkt)
                    else:
                        # Create empty polygon WKT if perimeter not found
                        wkt_geometries.append(Polygon([]).wkt)
                
                # Create raw data structure WITHOUT geometry column
                raw_data = {
                    'mesh_name': mesh_area_names,
                }
                
                return proj_wkt, raw_data, wkt_geometries
                
        except Exception as e:
            raise QgsProcessingException(f"Error reading mesh areas directly from HDF: {e}")

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Direct HDF Access to Bypass ras-commander CRS Issues ---
            feedback.pushInfo(f"Loading mesh area perimeters from {hdf_path}...")
            
            proj_wkt, raw_data, wkt_geometries = self._get_mesh_areas_direct(hdf_path)
            
            if raw_data is None or len(raw_data.get('mesh_name', [])) == 0:
                raise QgsProcessingException("No 2D mesh areas found in the HDF file.")
            
            # Create raw DataFrame (no geometry column yet)
            raw_df = pd.DataFrame({
                'mesh_name': raw_data['mesh_name']
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
        fields.append(QgsField("mesh_name", QMetaType.Type.QString, "Mesh Name"))

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
            raise QgsProcessingException("Could not create sink for output layer.")

        total_features = len(gdf)
        feedback.pushInfo(f"Processing {total_features} mesh area perimeters...")
        
        for i, (_, row) in enumerate(gdf.iterrows()):
            if feedback.isCanceled():
                break
            
            feature = QgsFeature()
            feature.setFields(fields)
            feature.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
            
            # Set attributes for all defined fields
            if 'mesh_name' in row and pd.notna(row['mesh_name']):
                feature.setAttribute("mesh_name", str(row['mesh_name']))
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 100 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        feedback.pushInfo(f"Successfully processed {total_features} mesh area perimeters")
        return {self.OUTPUT_LAYER: dest_id}