"""
This script generates a comprehensive summary knowledge base for the ras-commander library.
It processes the project files and creates a single output file:

ras-commander_fullrepo.txt:
   A comprehensive summary of all relevant project files, including their content
   and structure. This file provides an overview of the entire codebase, including
   all files and folders except those specified in OMIT_FOLDERS and OMIT_FILES.
"""

import os
from pathlib import Path
import json

# Configuration
OMIT_FOLDERS = [
    "ras_commander", "Bald Eagle Creek", "__pycache__", ".git", ".github", "tests", "docs", "library_assistant", "__pycache__", ".conda", "workspace"
    "build", "dist", "ras_commander.egg-info", "venv", "ras_commander.egg-info", "log_folder", "logs",
    "example_projects", "llm_knowledge_bases", "misc", "ai_tools", "FEMA_BLE_Models", "hdf_example_data", "ras_example_categories", "html", "data", "apidocs", "build", "dist", "ras_commander.egg-info", "venv", "log_folder", "logs",
]
OMIT_FILES = [
    ".pyc", ".pyo", ".pyd", ".dll", ".so", ".dylib", ".exe", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".ico", ".webp", ".svg", ".eps", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".odg", ".odf", ".odc", ".odm", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf", ".odg", ".odp", ".odc", ".odm", ".odf",
    ".bat", ".sh", ".log", ".tmp", ".bak", ".swp",
    ".DS_Store", "Thumbs.db", "example_projects.zip",
    "Example_Projects_6_6.zip", "example_projects.ipynb", "11_Using_RasExamples.ipynb", 
    "future_dev_roadmap.ipynb", "structures_attributes.csv", "example_projects.csv",
]
SUMMARY_OUTPUT_DIR = "llm_knowledge_bases"
SCRIPT_NAME = Path(__file__).name

def ensure_output_dir(base_path):
    output_dir = base_path / SUMMARY_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ensured to exist: {output_dir}")
    return output_dir

def should_omit(filepath):
    if filepath.name == SCRIPT_NAME:
        return True
    if any(omit_folder in filepath.parts for omit_folder in OMIT_FOLDERS):
        return True
    if any(filepath.suffix == ext or filepath.name == ext for ext in OMIT_FILES):
        return True
    return False

def read_file_contents(filepath):
    try:
        # Process Jupyter notebooks specially
        if filepath.suffix.lower() == '.ipynb':
            print(f"Processing notebook: {filepath}")
            with open(filepath, 'r', encoding='utf-8') as f:
                notebook = json.load(f)
                # Return simplified notebook without outputs
                return json.dumps(notebook, indent=2)
        
        # Regular file reading for other files
        with open(filepath, 'r', encoding='utf-8') as infile:
            content = infile.read()
            print(f"Reading content of file: {filepath}")
    except UnicodeDecodeError:
        with open(filepath, 'rb') as infile:
            content = infile.read().decode('utf-8', errors='ignore')
            print(f"Reading and converting content of file: {filepath}")
    return content

def generate_full_summary(summarize_subfolder, output_dir):
    output_file_name = f"{summarize_subfolder.name}_fullrepo.txt"
    output_file_path = output_dir / output_file_name
    print(f"Generating Full Summary: {output_file_path}")

    with open(output_file_path, 'w', encoding='utf-8') as outfile:
        for filepath in summarize_subfolder.rglob('*'):
            if should_omit(filepath):
                continue
            if filepath.is_file():
                outfile.write(f"File: {filepath}\n")
                outfile.write("="*50 + "\n")
                content = read_file_contents(filepath)
                outfile.write(content)
                outfile.write("\n" + "="*50 + "\n\n")
                print(f"Added file to full summary: {filepath}")
            elif filepath.is_dir():
                outfile.write(f"Folder: {filepath}\n")
                outfile.write("="*50 + "\n\n")
                print(f"Added folder to full summary: {filepath}")

    print(f"Full summary created at '{output_file_path}'")

def main():
    # Get the name of this script
    this_script = SCRIPT_NAME
    print(f"Script name: {this_script}")

    # Define the subfolder to summarize (parent of the script's parent)
    summarize_subfolder = Path(__file__).parent.parent
    print(f"Subfolder to summarize: {summarize_subfolder}")

    # Ensure the output directory exists
    output_dir = ensure_output_dir(Path(__file__).parent)

    # Delete all existing files in the output directory
    for file in output_dir.glob('*'):
        if file.is_file():
            file.unlink()

    # Generate full repo summary
    generate_full_summary(summarize_subfolder, output_dir)

    print(f"Full repository summary has been generated in '{output_dir}'")

if __name__ == "__main__":
    main()
