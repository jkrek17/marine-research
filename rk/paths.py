"""Where things live: the repository root, the shared data directory (truth, small results) and the local field cache."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("RK_DATA", "/mnt/project-files/research-data"))
CACHE = Path(os.environ.get("RK_CACHE") or Path.home() / ".cache" / "marine-research")


def cache(*parts):
    """Path under CACHE (the local model-field cache); creates the parent directories."""
    p = CACHE.joinpath(*[str(x) for x in parts])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def data(*parts):
    """Path under DATA; creates the parent directories so the caller can write at once."""
    p = DATA.joinpath(*[str(x) for x in parts])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
