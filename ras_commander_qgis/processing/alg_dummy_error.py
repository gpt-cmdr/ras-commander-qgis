# -*- coding: utf-8 -*-
"""
Dummy algorithm shown when ras-commander cannot be loaded.
"""

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingException
)


class DummyErrorAlgorithm(QgsProcessingAlgorithm):
    """
    Dummy algorithm that explains installation issues.
    """
    
    def createInstance(self):
        return DummyErrorAlgorithm()
    
    def name(self):
        return 'installation_error'
        
    def displayName(self):
        return 'RAS Commander Installation Error'
        
    def group(self):
        return 'Installation'
        
    def groupId(self):
        return 'installation'
        
    def shortHelpString(self):
        return """
        <h3>RAS Commander Installation Issue</h3>
        <p>The ras-commander library could not be loaded. This is required for all RAS Commander algorithms.</p>
        
        <h4>Installation Instructions:</h4>
        <ol>
        <li>Open OSGeo4W Shell as Administrator</li>
        <li>Run: <code>pip install ras-commander --no-deps</code></li>
        <li>Restart QGIS</li>
        </ol>
        
        <h4>Alternative Installation:</h4>
        <p>If you have a standard Python installation, you can install normally:</p>
        <code>pip install ras-commander</code>
        
        <h4>Common Issues:</h4>
        <ul>
        <li>HDF5 library conflicts - use --no-deps flag</li>
        <li>Permission issues - run as Administrator</li>
        <li>QGIS Python environment - ensure correct Python path</li>
        </ul>
        """
    
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterString(
                'DUMMY',
                'This algorithm cannot run',
                defaultValue='Please install ras-commander library'
            )
        )
        
    def processAlgorithm(self, parameters, context, feedback):
        raise QgsProcessingException(
            "ras-commander library is not installed. "
            "Please install it using: pip install ras-commander --no-deps"
        ) 