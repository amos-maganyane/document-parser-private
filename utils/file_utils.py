import os
from pathlib import Path

def validate_file_path(file_path: str) -> None:
    """Validate file exists and is accessible"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")
    if os.access(file_path, os.R_OK) is False:
        raise PermissionError(f"Access denied: {file_path}")