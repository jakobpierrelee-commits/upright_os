#!/usr/bin/env python3
"""Compatibility shim: use app/bridge/server.py as canonical runtime."""
from __future__ import annotations

import os
import runpy
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER = os.path.join(ROOT, "app", "bridge", "server.py")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if __name__ == "__main__":
    runpy.run_path(SERVER, run_name="__main__")
