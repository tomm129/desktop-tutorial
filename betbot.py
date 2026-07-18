#!/usr/bin/env python3
"""Lançador: permite rodar `python betbot.py <comando>` sem configurar PYTHONPATH."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from betbot.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
