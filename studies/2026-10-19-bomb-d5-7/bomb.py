"""The study's bomb rule now lives in rk/bomb.py (shared with the lab job); this keeps the study's imports working."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent / "2026-10-16-pressure-d5-7"))
from rk.bomb import (BELOW, BERGERON, BOXES, CELL, NBR_KM, PAD, SEP_KM, SIZE, TRACK_KM, bombs, cells,  # noqa: E402,F401
                     dec, dedupe, find_lows, member_field, near)
