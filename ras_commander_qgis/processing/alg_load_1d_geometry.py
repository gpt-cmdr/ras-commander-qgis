# -*- coding: utf-8 -*-
"""
Consolidated algorithm for loading 1D geometry elements from HEC-RAS HDF files.
This single algorithm replaces four separate algorithms for cross-sections,
river centerlines, bank lines, and hydraulic structures.
"""

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads

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
    QgsProcessingUtils,
    QgsVectorLayer,
    QgsProject
)
from PyQt5.QtCore import QMetaType
from .helpers import convert_complex_columns_to_string, move_layer_to_benefit_area_group

class Load1DGeometryAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 1D geometry elements from a HEC-RAS geometry HDF file.
    
    This tool can extract various 1D geometry types including cross-sections,
    river centerlines, bank lines, and hydraulic structures, loading them as
    line vector layers in QGIS. Multiple geometry types can be selected at once.
    """
    INPUT_HDF = 'INPUT_HDF'
    LOAD_CROSS_SECTIONS = 'LOAD_CROSS_SECTIONS'
    LOAD_CENTERLINES = 'LOAD_CENTERLINES'
    LOAD_BANK_LINES = 'LOAD_BANK_LINES'
    LOAD_STRUCTURES = 'LOAD_STRUCTURES'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_CROSS_SECTIONS = 'OUTPUT_CROSS_SECTIONS'
    OUTPUT_CENTERLINES = 'OUTPUT_CENTERLINES'
    OUTPUT_BANK_LINES = 'OUTPUT_BANK_LINES'
    OUTPUT_STRUCTURES = 'OUTPUT_STRUCTURES'

    def createInstance(self):
        return Load1DGeometryAlgorithm()

    def name(self):
        return 'load_1d_geometry'

    def displayName(self):
        return 'Load 1D Geometry Elements'

    def group(self):
        return '1D Geometry Layers'

    def groupId(self):
        return 'ras_1d_geometry'

    def shortHelpString(self):
        return """
        <h3>Load 1D Geometry Elements</h3>
        <p>This algorithm loads various 1D geometry elements from a HEC-RAS geometry or plan HDF file.</p>
        
        <h4>Available Geometry Types (select one or more):</h4>
        <ul>
        <li><b>Cross-Sections:</b> 1D cross-section cut lines with station-elevation data, Manning's n values, and hydraulic parameters</li>
        <li><b>River Centerlines:</b> River/reach centerline geometries</li>
        <li><b>Bank Lines:</b> Left and right bank line geometries</li>
        <li><b>Hydraulic Structures:</b> Bridges, culverts, weirs, and other structures</li>
        </ul>
        
        <h4>Parameters:</h4>
        <ul>
        <li><b>Geometry Types:</b> Select one or more types of 1D geometry to load. Each selected type will create a separate output layer.</li>
        <li><b>Override CRS:</b> Optional coordinate reference system to use if the HDF file lacks CRS information</li>
        </ul>
        """

    def postProcessAlgorithm(self, context: QgsProcessingContext, feedback):
        """Post-process to move certain layers to the Benefit Area Analysis group."""
        results = super().postProcessAlgorithm(context, feedback) or {}
        
        # Move centerlines and structures to Benefit Area Analysis group
        layers_to_move = []
        if self.OUTPUT_CENTERLINES in results and results[self.OUTPUT_CENTERLINES]:
            layers_to_move.append((results[self.OUTPUT_CENTERLINES], 'River Centerlines'))
        if self.OUTPUT_STRUCTURES in results and results[self.OUTPUT_STRUCTURES]:
            layers_to_move.append((results[self.OUTPUT_STRUCTURES], 'Hydraulic Structures'))
            
        for layer_id, layer_name in layers_to_move:
            layer = QgsProcessingUtils.mapLayerFromString(layer_id, context)
            if layer:
                success = move_layer_to_benefit_area_group(layer.id())
                if success:
                    feedback.pushInfo(f"{layer_name} layer moved to 'Benefit Area Analysis' group")
        
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
                self.LOAD_CROSS_SECTIONS,
                'Load Cross-Sections',
                defaultValue=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_CENTERLINES,
                'Load River Centerlines',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_BANK_LINES,
                'Load Bank Lines',
                defaultValue=False
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_STRUCTURES,
                'Load Hydraulic Structures',
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
                self.OUTPUT_CROSS_SECTIONS,
                'Cross-Sections Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_CENTERLINES,
                'River Centerlines Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_BANK_LINES,
                'Bank Lines Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_STRUCTURES,
                'Hydraulic Structures Output',
                type=QgsProcessing.TypeVectorLine,
                optional=True
            )
        )

    def _load_cross_sections(self, hdf_path, feedback):
        """Load cross-sections from HDF file."""
        from ras_commander import HdfXsec
        feedback.pushInfo(f"Loading cross-sections from {hdf_path}...")
        
        initial_gdf = HdfXsec.get_cross_sections(hdf_path)
        if initial_gdf is None or initial_gdf.empty:
            feedback.pushWarning("No cross-sections found in the specified HDF file.")
            return None
        
        return initial_gdf

    def _load_centerlines(self, hdf_path, feedback):
        """Load river centerlines from HDF file."""
        from ras_commander import HdfXsec
        feedback.pushInfo(f"Loading river centerlines from {hdf_path}...")
        
        initial_gdf = HdfXsec.get_river_centerlines(hdf_path)
        if initial_gdf is None or initial_gdf.empty:
            feedback.pushWarning("No river centerlines found in the specified HDF file.")
            return None
        
        return initial_gdf

    def _load_bank_lines(self, hdf_path, feedback):
        """Load bank lines from HDF file."""
        from ras_commander import HdfXsec
        feedback.pushInfo(f"Loading bank lines from {hdf_path}...")
        
        initial_gdf = HdfXsec.get_river_bank_lines(hdf_path)
        if initial_gdf is None or initial_gdf.empty:
            feedback.pushWarning("No bank lines found in the HDF file.")
            return None
        
        return initial_gdf

    def _load_structures(self, hdf_path, feedback):
        """Load hydraulic structures from HDF file."""
        from ras_commander import HdfStruc
        feedback.pushInfo(f"Loading hydraulic structures from {hdf_path}...")
        
        initial_gdf = HdfStruc.get_structures(hdf_path)
        if initial_gdf is None or initial_gdf.empty:
            feedback.pushWarning("No hydraulic structures found in the HDF file.")
            return None
        
        return initial_gdf

    def _get_fields_for_geometry_type(self, geom_type):
        """Get the appropriate fields definition for each geometry type."""
        fields = QgsFields()
        
        if geom_type == 'cross_sections':
            fields.append(QgsField("River", QMetaType.Type.QString))
            fields.append(QgsField("Reach", QMetaType.Type.QString))
            fields.append(QgsField("RS", QMetaType.Type.QString))
            fields.append(QgsField("Left Bank", QMetaType.Type.Double))
            fields.append(QgsField("Right Bank", QMetaType.Type.Double))
            fields.append(QgsField("station_elevation", QMetaType.Type.QString, 'station_elevation', 0, 0, 'Station-Elevation Profile'))
            fields.append(QgsField("mannings_n", QMetaType.Type.QString, 'mannings_n', 0, 0, "Manning's n Profile"))
            fields.append(QgsField("ineffective_blocks", QMetaType.Type.QString, 'ineffective_blocks', 0, 0, "Ineffective Flow Areas"))
            
        elif geom_type == 'centerlines':
            fields.append(QgsField("River Name", QMetaType.Type.QString))
            fields.append(QgsField("Reach Name", QMetaType.Type.QString))
            
        elif geom_type == 'bank_lines':
            fields.append(QgsField("bank_id", QMetaType.Type.Int))
            fields.append(QgsField("bank_side", QMetaType.Type.QString))
            fields.append(QgsField("length", QMetaType.Type.Double))
            
        elif geom_type == 'structures':
            fields.append(QgsField("River", QMetaType.Type.QString))
            fields.append(QgsField("Reach", QMetaType.Type.QString))
            fields.append(QgsField("RS", QMetaType.Type.QString))
            fields.append(QgsField("Type", QMetaType.Type.QString))
        
        return fields

    def _process_geometry_type(self, gdf, geom_type, proj_wkt, parameters, context, feedback):
        """Process a single geometry type and return the output layer ID."""
        if gdf is None:
            return None
            
        # Convert complex columns for cross-sections
        if geom_type == 'cross_sections':
            complex_cols = ['station_elevation', 'mannings_n', 'ineffective_blocks']
            gdf = convert_complex_columns_to_string(gdf, complex_cols)

        # Get appropriate fields for the geometry type
        fields = self._get_fields_for_geometry_type(geom_type)
        
        # Create QGIS CRS object
        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        # Map geometry type to output parameter
        output_param_map = {
            'cross_sections': self.OUTPUT_CROSS_SECTIONS,
            'centerlines': self.OUTPUT_CENTERLINES,
            'bank_lines': self.OUTPUT_BANK_LINES,
            'structures': self.OUTPUT_STRUCTURES
        }
        
        output_param = output_param_map[geom_type]
        
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            output_param,
            context,
            fields,
            QgsWkbTypes.LineString,
            qgis_crs
        )

        if sink is None:
            return None

        # Add features to the sink
        total_features = len(gdf)
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
                    feature.setAttribute(col_name, row[col_name])
            
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            # Progress updates are handled by main process method

        return dest_id

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)
        
        # Check which geometry types to load
        load_cross_sections = self.parameterAsBoolean(parameters, self.LOAD_CROSS_SECTIONS, context)
        load_centerlines = self.parameterAsBoolean(parameters, self.LOAD_CENTERLINES, context)
        load_bank_lines = self.parameterAsBoolean(parameters, self.LOAD_BANK_LINES, context)
        load_structures = self.parameterAsBoolean(parameters, self.LOAD_STRUCTURES, context)
        
        # Check if at least one geometry type is selected
        if not any([load_cross_sections, load_centerlines, load_bank_lines, load_structures]):
            raise QgsProcessingException("Please select at least one geometry type to load.")
        
        # Determine CRS from the first available geometry
        proj_wkt = None
        crs_name = None
        
        # Try to get CRS from any geometry type
        test_funcs = []
        if load_cross_sections:
            test_funcs.append(self._load_cross_sections)
        if load_centerlines:
            test_funcs.append(self._load_centerlines)
        if load_bank_lines:
            test_funcs.append(self._load_bank_lines)
        if load_structures:
            test_funcs.append(self._load_structures)
            
        for func in test_funcs:
            try:
                test_gdf = func(hdf_path, feedback)
                if test_gdf is not None and not test_gdf.empty and test_gdf.crs:
                    proj_wkt = test_gdf.crs.to_wkt()
                    crs_name = test_gdf.crs.name
                    feedback.pushInfo(f"CRS found in HEC-RAS project: {crs_name}")
                    break
            except:
                continue
                
        if not proj_wkt:
            if override_crs and override_crs.isValid():
                proj_wkt = override_crs.toWkt()
                feedback.pushInfo(f"Using user-defined override CRS: {override_crs.authid()}")
            else:
                raise QgsProcessingException(
                    "Coordinate Reference System (CRS) could not be determined. "
                    "Please define the CRS in your HEC-RAS model using RAS Mapper, "
                    "or provide a valid Override CRS in the tool dialog."
                )
        
        results = {}
        total_steps = sum([load_cross_sections, load_centerlines, load_bank_lines, load_structures])
        current_step = 0
        
        # Process each selected geometry type
        if load_cross_sections:
            try:
                initial_gdf = self._load_cross_sections(hdf_path, feedback)
                if initial_gdf is not None:
                    # Apply firewall pattern
                    wkt_geometries = initial_gdf.geometry.to_wkt()
                    raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
                    geometry = [loads(wkt) for wkt in wkt_geometries]
                    gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)
                    
                    dest_id = self._process_geometry_type(gdf, 'cross_sections', proj_wkt, parameters, context, feedback)
                    if dest_id:
                        results[self.OUTPUT_CROSS_SECTIONS] = dest_id
                        feedback.pushInfo(f"Successfully loaded {len(gdf)} cross-sections.")
            except Exception as e:
                feedback.pushWarning(f"Failed to load cross-sections: {e}")
            current_step += 1
            feedback.setProgress(int((current_step / total_steps) * 100))
            
        if load_centerlines:
            try:
                initial_gdf = self._load_centerlines(hdf_path, feedback)
                if initial_gdf is not None:
                    # Apply firewall pattern
                    wkt_geometries = initial_gdf.geometry.to_wkt()
                    raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
                    geometry = [loads(wkt) for wkt in wkt_geometries]
                    gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)
                    
                    dest_id = self._process_geometry_type(gdf, 'centerlines', proj_wkt, parameters, context, feedback)
                    if dest_id:
                        results[self.OUTPUT_CENTERLINES] = dest_id
                        feedback.pushInfo(f"Successfully loaded {len(gdf)} river centerlines.")
            except Exception as e:
                feedback.pushWarning(f"Failed to load river centerlines: {e}")
            current_step += 1
            feedback.setProgress(int((current_step / total_steps) * 100))
            
        if load_bank_lines:
            try:
                initial_gdf = self._load_bank_lines(hdf_path, feedback)
                if initial_gdf is not None:
                    # Apply firewall pattern
                    wkt_geometries = initial_gdf.geometry.to_wkt()
                    raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
                    geometry = [loads(wkt) for wkt in wkt_geometries]
                    gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)
                    
                    dest_id = self._process_geometry_type(gdf, 'bank_lines', proj_wkt, parameters, context, feedback)
                    if dest_id:
                        results[self.OUTPUT_BANK_LINES] = dest_id
                        feedback.pushInfo(f"Successfully loaded {len(gdf)} bank lines.")
            except Exception as e:
                feedback.pushWarning(f"Failed to load bank lines: {e}")
            current_step += 1
            feedback.setProgress(int((current_step / total_steps) * 100))
            
        if load_structures:
            try:
                initial_gdf = self._load_structures(hdf_path, feedback)
                if initial_gdf is not None:
                    # Apply firewall pattern
                    wkt_geometries = initial_gdf.geometry.to_wkt()
                    raw_df = pd.DataFrame(initial_gdf.drop(columns='geometry'))
                    geometry = [loads(wkt) for wkt in wkt_geometries]
                    gdf = gpd.GeoDataFrame(raw_df, geometry=geometry)
                    
                    dest_id = self._process_geometry_type(gdf, 'structures', proj_wkt, parameters, context, feedback)
                    if dest_id:
                        results[self.OUTPUT_STRUCTURES] = dest_id
                        feedback.pushInfo(f"Successfully loaded {len(gdf)} hydraulic structures.")
            except Exception as e:
                feedback.pushWarning(f"Failed to load hydraulic structures: {e}")
            current_step += 1
            feedback.setProgress(int((current_step / total_steps) * 100))
        
        if not results:
            raise QgsProcessingException("No geometry data could be loaded from the HDF file.")
            
        return results