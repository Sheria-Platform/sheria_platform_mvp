"""
Automatically discovers and imports all modules in the models package.

This module initialization script dynamically imports all Python modules found in the
same directory as this __init__.py file. This ensures that all model classes are
registered and available when the models package is imported, which is particularly
useful for ORM frameworks that require model classes to be imported for proper
registration and table creation.

The script performs the following steps:
1. Determines the directory path of the current package
2. Iterates through all modules in that directory
3. Dynamically imports each discovered module

Note: This is a module-level script, not a function. It executes automatically when
the package is imported.
"""
import importlib
import pkgutil
from pathlib import Path

# Resolve the absolute path of the directory containing this __init__.py file
package_dir = Path(__file__).resolve().parent

# Iterate through all modules in the package directory and import them
for module in pkgutil.iter_modules([str(package_dir)]):
    importlib.import_module(f"{__name__}.{module.name}")