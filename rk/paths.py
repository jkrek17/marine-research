"""Where things live: the repository root and the shared data directory."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("RK_DATA", "/mnt/project-files/research-data"))


def data(*parts):
    """Path under DATA; creates the parent directories so the caller can write at once."""
    p = DATA.joinpath(*[str(x) for x in parts])
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
