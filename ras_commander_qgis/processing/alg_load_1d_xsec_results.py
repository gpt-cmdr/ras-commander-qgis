# ras_commander_qgis/processing/alg_load_1d_xsec_results.py
# -*- coding: utf-8 -*-

import pandas as pd
import geopandas as gpd
from shapely.wkt import loads
from qgis.PyQt.QtCore import QDateTime

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

class Load1DCrossSectionResultsAlgorithm(QgsProcessingAlgorithm):
    """
    Loads 1D cross-section time series results from a HEC-RAS plan HDF file.
    
    This tool creates a single, time-enabled vector layer containing results
    (Water Surface, Flow, Velocity) for each cross-section at each time step.
    
    Use the QGIS Temporal Controller to visualize the results.
    """
    INPUT_HDF = 'INPUT_HDF'
    OVERRIDE_CRS = 'OVERRIDE_CRS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    def createInstance(self):
        return Load1DCrossSectionResultsAlgorithm()

    def name(self):
        return 'load_1d_xsec_results'

    def displayName(self):
        return 'Load 1D Cross-Section Results (Time Series)'

    def group(self):
        return '1D Summary Results'

    def groupId(self):
        return 'ras_1d_summary_results'

    def shortHelpString(self):
        return """
        <h3>Load 1D Cross-Section Results (Time Series)</h3>
        <p>This algorithm loads time series results for 1D cross-sections from a HEC-RAS plan HDF file (*.p##.hdf).</p>
        <p>It creates a single line layer where each feature represents a cross-section at a specific time step. The layer includes attributes for water surface, flow, and velocity.</p>
        <h4>Usage:</h4>
        <p>After running the tool, enable the QGIS Temporal Controller to animate the results:</p>
        <ol>
        <li>Right-click the output layer ('1D Cross-Section Results') and go to <b>Properties</b>.</li>
        <li>Select the <b>Temporal</b> tab.</li>
        <li>Check the <b>Enable Temporal Control</b> box.</li>
        <li>Choose <b>Single Field with Date/Time</b>.</li>
        <li>Set the <b>Field</b> to 'timestamp'.</li>
        <li>Click <b>OK</b>.</li>
        <li>Open the Temporal Controller panel (View -> Panels -> Temporal Controller Panel) and press the play button.</li>
        </ol>
        """

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
            QgsProcessingParameterCrs(
                self.OVERRIDE_CRS,
                'Override CRS (Optional)',
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                '1D Results: Summary',
                QgsProcessing.TypeVectorLine
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        hdf_path = self.parameterAsFile(parameters, self.INPUT_HDF, context)
        override_crs = self.parameterAsCrs(parameters, self.OVERRIDE_CRS, context)

        try:
            # --- Firewall Step 1: Load data using ras-commander ---
            from ras_commander import HdfResultsXsec, HdfXsec
            feedback.pushInfo("Loading cross-section time series results...")
            
            # First check if we have cross-section geometries
            initial_geom_gdf = HdfXsec.get_cross_sections(hdf_path)
            if initial_geom_gdf is None or initial_geom_gdf.empty:
                raise QgsProcessingException("No 1D cross-section geometries found in the HDF file. This algorithm requires a HDF file with 1D cross-section data.")
            
            feedback.pushInfo(f"Found {len(initial_geom_gdf)} cross-sections, loading time series results...")
            
            # Load results (xarray)
            results_xr = HdfResultsXsec.get_xsec_timeseries(hdf_path)
            if results_xr is None or not results_xr.data_vars:
                raise QgsProcessingException("No 1D cross-section time series results found in the HDF file. This algorithm requires a HDF file with 1D unsteady flow results.")

            # --- Firewall Step 2: Deconstruct and Handle CRS ---
            proj_wkt = initial_geom_gdf.crs.to_wkt() if initial_geom_gdf.crs else None
            crs_name = initial_geom_gdf.crs.name if initial_geom_gdf.crs else None
            
            if not proj_wkt and override_crs and override_crs.isValid():
                proj_wkt = override_crs.toWkt()
                crs_name = override_crs.authid()
                feedback.pushInfo(f"Using user-defined override CRS: {crs_name}")
            elif proj_wkt:
                feedback.pushInfo(f"CRS found in HEC-RAS project: {crs_name}")
            else:
                 raise QgsProcessingException("CRS could not be determined. Please provide an Override CRS.")

            # Deconstruct geometry GeoDataFrame
            geom_wkt = initial_geom_gdf.geometry.to_wkt()
            geom_df = pd.DataFrame(initial_geom_gdf.drop(columns='geometry'))
            
        except QgsProcessingException as e:
            raise e
        except Exception as e:
            # Check if this is a 2D-only model
            error_msg = str(e)
            if "component not found" in error_msg.lower() or "unable to synchronously open object" in error_msg.lower():
                raise QgsProcessingException(
                    "Could not find 1D cross-section time series results in this HDF file. "
                    "This error typically occurs when:\n"
                    "1. The HDF file contains only 2D model results (no 1D components)\n"
                    "2. The model was run as steady flow (no time series data)\n"
                    "3. The 1D results are stored in a different location\n\n"
                    "Please verify that your HDF file contains 1D unsteady flow results. "
                    "For 2D-only models, use the '2D Vector Results' algorithms instead."
                )
            else:
                raise QgsProcessingException(f"Failed during initial data load: {e}")

        try:
            # --- Step 3: Reshape data and merge ---
            feedback.pushInfo("Reshaping time series data...")
            # Convert xarray to long-format DataFrame, dropping NaN values
            results_df = results_xr.to_dataframe().reset_index().dropna()

            # Reconstruct safe geometry GeoDataFrame
            geometry = [loads(wkt) for wkt in geom_wkt]
            geom_gdf = gpd.GeoDataFrame(geom_df, geometry=geometry)
            
            # Merge results with geometries based on the cross-section identifier
            # The 'cross_section' coordinate in xarray matches the 'Name' field in geometry
            merged_gdf = results_df.merge(geom_gdf, left_on='cross_section', right_on='Name', how='inner')
            feedback.pushInfo(f"After merge: {len(merged_gdf)} features from {len(results_df)} results and {len(geom_gdf)} geometries")

        except Exception as e:
            raise QgsProcessingException(f"Failed during data processing and merging: {e}")
            
        # --- Step 4: Write to QGIS Layer using Feature Sink ---
        fields = QgsFields()
        fields.append(QgsField("timestamp", QMetaType.Type.QDateTime))
        fields.append(QgsField("River", QMetaType.Type.QString))
        fields.append(QgsField("Reach", QMetaType.Type.QString))
        fields.append(QgsField("RS", QMetaType.Type.QString))
        fields.append(QgsField("WSE", QMetaType.Type.Double, "Water Surface Elevation"))
        fields.append(QgsField("Flow", QMetaType.Type.Double))
        fields.append(QgsField("Vel_Total", QMetaType.Type.Double, "Total Velocity"))
        fields.append(QgsField("Vel_Channel", QMetaType.Type.Double, "Channel Velocity"))
        fields.append(QgsField("Flow_Lateral", QMetaType.Type.Double, "Lateral Flow"))

        qgis_crs = QgsCoordinateReferenceSystem()
        qgis_crs.createFromWkt(proj_wkt)

        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT_LAYER, context, fields, QgsWkbTypes.LineString, qgis_crs
        )

        if sink is None:
            raise QgsProcessingException("Could not create sink for output layer.")

        total_features = len(merged_gdf)
        feedback.pushInfo(f"Writing {total_features} features (time steps * cross-sections)...")
        
        for i, (_, row) in enumerate(merged_gdf.iterrows()):
            if feedback.isCanceled():
                break

            # Skip features with missing geometry
            if row['geometry'] is None:
                continue

            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromWkt(row['geometry'].wkt)) # Use merged geometry
            
            # Use QDateTime for the timestamp field
            dt = QDateTime(row['time'])
            feature.setAttributes([
                dt,
                row['River'],
                row['Reach'],
                row['RS'],
                row['Water_Surface'],
                row['Flow'],
                row['Velocity_Total'],
                row['Velocity_Channel'],
                row['Flow_Lateral']
            ])

            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            if i % 5000 == 0:
                feedback.setProgress(int((i / total_features) * 100))
        
        if feedback.isCanceled():
            return {}

        return {self.OUTPUT_LAYER: dest_id}