#!/usr/bin/env python3
"""Compatibility shim: re-export canonical gateway from app.bridge."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.bridge.serial_gateway import *  # noqa: F401,F403
