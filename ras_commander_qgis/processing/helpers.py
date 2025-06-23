# ras_commander_qgis/processing/helpers.py
# -*- coding: utf-8 -*-
"""
Helper utilities for QGIS field creation and data type conversion.
This file has been updated to use modern QGIS 3.38+ compatible APIs.
"""
import numpy as np
import pandas as pd
from qgis.core import QgsField, QgsVectorLayer, QgsFeature, QgsProject
from PyQt5.QtCore import QMetaType


def pandas_dtype_to_qgs_field(col_name: str, dtype) -> QgsField:
    """
    Returns a QgsField with the correct QMetaType based on a pandas dtype.
    This provides a consistent mapping for creating fields, compatible with QGIS 3.38+.

    Args:
        col_name: The name of the column/field.
        dtype: The pandas dtype of the column.

    Returns:
        A configured QgsField instance using QMetaType.Type.
    """
    if pd.api.types.is_integer_dtype(dtype):
        return QgsField(col_name, QMetaType.Type.Int)
    elif pd.api.types.is_float_dtype(dtype):
        return QgsField(col_name, QMetaType.Type.Double)
    elif pd.api.types.is_bool_dtype(dtype):
        return QgsField(col_name, QMetaType.Type.Bool)
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return QgsField(col_name, QMetaType.Type.QDateTime)
    else:
        # Default to string for object, category, etc.
        return QgsField(col_name, QMetaType.Type.QString)


def convert_complex_columns_to_string(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Converts specified DataFrame columns containing complex objects (lists, dicts)
    to their string representation for QGIS compatibility.

    Args:
        df: Input DataFrame.
        columns: A list of column names to convert.

    Returns:
        A new DataFrame with the specified columns converted to strings.
    """
    df_copy = df.copy()
    for col in columns:
        if col in df_copy.columns:
            # Ensure all values are safely converted to string
            df_copy[col] = df_copy[col].apply(lambda x: str(x) if x is not None else None)
    return df_copy


def df_to_qgis_table(df: pd.DataFrame, layer_name: str) -> QgsVectorLayer:
    """
    Converts a pandas DataFrame into a QGIS table (non-spatial memory layer).
    This function is intended for algorithms that produce multiple table outputs,
    such as LoadProjectSummaryAlgorithm. Other single-output algorithms should
    use the more robust Feature Sink pattern.

    Args:
        df: The pandas DataFrame to convert.
        layer_name: The desired name for the QGIS layer.

    Returns:
        A non-spatial QgsVectorLayer instance populated with the DataFrame's data.
    """
    # Create a non-spatial layer
    layer = QgsVectorLayer('NoGeometry?encoding=UTF-8', layer_name, 'memory')
    prov = layer.dataProvider()

    # Define fields based on DataFrame dtypes, using the modern QMetaType helper
    fields = [pandas_dtype_to_qgs_field(col, dtype) for col, dtype in df.dtypes.items()]
    prov.addAttributes(fields)
    layer.updateFields()

    # Create features and populate them
    features = []
    for _, row in df.iterrows():
        feat = QgsFeature(layer.fields())
        for col_name in df.columns:
            value = row[col_name]
            if pd.isna(value):
                feat.setAttribute(col_name, None)
            else:
                # Coerce numpy types to standard Python types for safety
                if isinstance(value, np.integer):
                    feat.setAttribute(col_name, int(value))
                elif isinstance(value, np.floating):
                    feat.setAttribute(col_name, float(value))
                else:
                    feat.setAttribute(col_name, value)
        features.append(feat)

    prov.addFeatures(features)
    layer.updateExtents()
    return layer


def move_layer_to_benefit_area_group(layer_id: str) -> bool:
    """
    Moves a layer to the 'Benefit Area Analysis' group in the QGIS Layers panel.
    This is a convenience function for algorithms that create layers for benefit area analysis.
    
    Args:
        layer_id: The ID of the layer to move.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    return move_layer_to_group(layer_id, "Benefit Area Analysis")


def move_layer_to_group(layer_id: str, group_name: str) -> bool:
    """
    Moves a layer to a specified group in the QGIS Layers panel.
    Creates the group if it doesn't exist.
    
    Args:
        layer_id: The ID of the layer to move.
        group_name: The name of the target group.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        # Get the layer tree root
        root = QgsProject.instance().layerTreeRoot()
        
        # Find or create the group
        group = root.findGroup(group_name)
        
        if group is None:
            # Create the group at the top of the layer tree
            group = root.insertGroup(0, group_name)
        
        # Get the layer
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return False
        
        # Find the layer in the tree
        layer_tree_layer = root.findLayer(layer_id)
        if layer_tree_layer is None:
            return False
        
        # Clone the layer node and add it to the group
        cloned_layer = layer_tree_layer.clone()
        group.insertChildNode(0, cloned_layer)
        
        # Remove the original layer node from its current location
        layer_tree_layer.parent().removeChildNode(layer_tree_layer)
        
        return True
        
    except Exception as e:
        return False