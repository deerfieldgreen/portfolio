"""Standardized logging configuration for market session volume pipeline."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_logging(name: str) -> logging.Logger:
    """
    Unified logging setup with structured format.
    
    Args:
        name: Logger name (typically module name)
        
    Returns:
        Configured logger instance
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Format: "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
    formatter = logging.Formatter(
        "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if workspace directory exists)
    workspace_dir = os.getenv("WORKSPACE_DIR", "/workspace")
    log_dir = Path(workspace_dir) / "logs"
    
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{name}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        # If we can't write to workspace, just use console
        logger.warning(f"Could not create file handler: {e}")
    
    return logger
