import os
import shutil
import sys

def deploy_plugin():
    # Define source and destination paths
    source = r"C:\GH\ras-commander-qgis\ras_commander_qgis"
    destination = r"C:\Users\billk\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\ras_commander_qgis"
    
    print(f"Deploying plugin...")
    print(f"Source: {source}")
    print(f"Destination: {destination}")
    print("-" * 50)
    
    # Check if source exists
    if not os.path.exists(source):
        print(f"ERROR: Source directory does not exist: {source}")
        sys.exit(1)
    
    # Remove destination directory if it exists
    if os.path.exists(destination):
        try:
            print(f"Removing existing plugin directory...")
            shutil.rmtree(destination)
            print(f"✓ Successfully removed: {destination}")
        except Exception as e:
            print(f"ERROR: Failed to remove destination directory: {e}")
            sys.exit(1)
    else:
        print(f"Destination directory does not exist, skipping removal.")
    
    # Copy source to destination
    try:
        print(f"Copying plugin to destination...")
        shutil.copytree(source, destination)
        print(f"✓ Successfully copied plugin to: {destination}")
    except Exception as e:
        print(f"ERROR: Failed to copy plugin: {e}")
        sys.exit(1)
    
    print("-" * 50)
    print("✓ Plugin deployment completed successfully!")
    print("\nYou may need to restart QGIS or reload the plugin for changes to take effect.")

if __name__ == "__main__":
    deploy_plugin()