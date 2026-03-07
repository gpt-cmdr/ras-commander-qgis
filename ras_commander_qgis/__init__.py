# -*- coding: utf-8 -*-
"""
ras-commander-qgis: QGIS Plugin for HEC-RAS Data Access

An open-source project of CLB Engineering Corporation (https://clbengineering.com/)
GitHub: https://github.com/gpt-cmdr/ras-commander-qgis
Contact: info@clbengineering.com

Provides access to HEC-RAS model data through the ras-commander library.
"""

__author__ = "CLB Engineering Corporation"

def classFactory(iface):
    """Load RASCommanderPlugin class from plugin_main.
    
    Args:
        iface: A QGIS interface instance.
        
    Returns:
        The plugin instance.
    """
    from .plugin_main import RASCommanderPlugin
    return RASCommanderPlugin(iface) 