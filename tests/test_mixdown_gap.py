"""rk.features.mixdown_gap: strong 925 over a weak 10 m wind in unstable air."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402
from rk import features  # noqa: E402


def test_gap():
    s925 = np.array([40, 40, 40, 34.9, 40, np.nan])
    ten = np.array([15, 25, 15, 15, 15, 15])
    sa = np.array([10, 10, 4.9, 10, 5.0, 10])
    assert features.mixdown_gap(s925, ten, sa).tolist() == [True, False, False, False, True, False]
    assert features.mixdown_gap(s925, ten, sa, s925_kt=30).tolist()[3] is True


if __name__ == "__main__":
    test_gap()
    print("ok")
