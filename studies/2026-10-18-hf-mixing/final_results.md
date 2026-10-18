# Held-out weeks (scored once)

Method: logistic. Counts: {'cells': 5515, 'cells64': 1146, 'weeks': 5, 'storms': 13, 'storms64': 7}

| | ROC area |
|---|---|
| model | 0.801 |
| s925 | 0.653 |
| P | 0.805 |

Model minus s925: +0.149 [-0.069, +0.189]
Model minus live P: -0.004 [-0.106, +0.064]
Brier skill (vs held-out base rate): 0.093

Scores pass: False (signs are judged in findings.md)
