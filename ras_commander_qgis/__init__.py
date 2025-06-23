# -*- coding: utf-8 -*-
"""
RAS Commander QGIS Plugin

Provides access to HEC-RAS model data through the ras-commander library.
"""

def classFactory(iface):
    """Load RASCommanderPlugin class from plugin_main.
    
    Args:
        iface: A QGIS interface instance.
        
    Returns:
        The plugin instance.
    """
    from .plugin_main import RASCommanderPlugin
    return RASCommanderPlugin(iface) 