# -*- coding: utf-8 -*-
"""
Main plugin class for RAS Commander QGIS Plugin.
"""

from PyQt5.QtCore import QCoreApplication
from qgis.core import QgsApplication, QgsMessageLog, Qgis


class RASCommanderPlugin:
    """Main plugin class that handles lifecycle and provider registration."""
    
    def __init__(self, iface):
        """Initialize the plugin.
        
        Args:
            iface: A reference to the QgisInterface.
        """
        self.iface = iface
        self.provider = None

    def initProcessing(self):
        """Initialize Processing provider."""
        try:
            # Lazy import to avoid import errors on plugin load
            from .processing.provider import RASCommanderProvider
            self.provider = RASCommanderProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)
        except ImportError as e:
            QgsMessageLog.logMessage(
                f"Failed to load RAS Commander provider: {e}",
                "RAS Commander",
                Qgis.Warning
            )
            # Show a user-friendly message
            if self.iface:
                self.iface.messageBar().pushMessage(
                    "RAS Commander",
                    "Could not load ras-commander library. Please install it using: pip install ras-commander",
                    Qgis.Warning,
                    duration=10
                )

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        self.initProcessing()

    def unload(self):
        """Remove the plugin menu item and icon from QGIS GUI."""
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def tr(self, message):
        """Get the translation for a string using Qt translation API.
        
        We implement this ourselves since we do not inherit QObject.
        
        Args:
            message: String for translation.
            
        Returns:
            Translated version of message.
        """
        return QCoreApplication.translate('RASCommander', message) 