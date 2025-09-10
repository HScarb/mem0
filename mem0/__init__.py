import importlib.metadata

__version__ = importlib.metadata.version("mem0ai")

import logging

import os

from mem0.client.main import AsyncMemoryClient, MemoryClient  # noqa
from mem0.memory.main import AsyncMemory, Memory  # noqa

# Define log directory and file path
log_dir = "logs"
log_file = os.path.join(log_dir, "mem0.log")

# Create log directory if it doesn't exist
os.makedirs(log_dir, exist_ok=True)

# Configure logging to write to a file
logging.basicConfig(
    level=logging.INFO,
    filename=log_file,
    filemode='a',  # 'a' for append, 'w' for overwrite
    format='%(asctime)s - %(levelname)s - %(message)s'
)
