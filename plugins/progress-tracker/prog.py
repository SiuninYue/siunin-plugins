#!/usr/bin/env python3
"""
Progress Tracker CLI Python entry point
Forwards all arguments to the bash 'prog' script.
This allows AI/automation to call 'python prog.py' directly.
"""

import sys
import subprocess
import os

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
prog_script = os.path.join(script_dir, "prog")

# Re-execute with bash, passing all arguments
result = subprocess.call(["bash", prog_script] + sys.argv[1:])
sys.exit(result)
