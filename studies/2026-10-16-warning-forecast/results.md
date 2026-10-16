Hours with a fully parsed desk text only. Tune weeks pick the rule; held-out weeks are read once.

## Gale (34 kt)

Desk, tune weeks: detection 97% of 1574 events, FA area 66%, FA areas 20%, area 1271409 nm2

| rule | setting | tune detection | held-out detection [90%] | held-out FA area | held-out area nm2 |
|---|---|---|---|---|---|
| lift0.3 | 2.0 | 81% | 82% [77-87] | 3% | 170182 |
| lift0.3 | 3.0 | 81% | 83% [77-88] | 3% | 172718 |
| lift0.3 | 5.0 | 81% | 83% [77-88] | 3% | 173980 |
| lift0.3 | 12.0 | 81% | 83% [77-88] | 3% | 174461 |
| lift0.3 | 8.0 | 81% | 83% [77-88] | 3% | 174341 |
| lift0.3 | 10.0 | 81% | 83% [77-88] | 3% | 174423 |
| desk | | 97% | 98% [96-99] | 70% | 1461280 |

By month, all weeks (best rule lift0.3 2.0 vs desk): detection, events
- 202511: 79% vs desk 97%, 358 events
- 202512: 81% vs desk 97%, 590 events
- 202601: 81% vs desk 98%, 395 events
- 202602: 85% vs desk 98%, 408 events
- 202603: 80% vs desk 96%, 339 events

## Storm (48 kt)

Desk, tune weeks: detection 81% of 414 events, FA area 66%, FA areas 28%, area 144832 nm2

| rule | setting | tune detection | held-out detection [90%] | held-out FA area | held-out area nm2 |
|---|---|---|---|---|---|
| model_ifs | 6.0 | 84% | 88% [79-96] | 8% | 12179 |
| blend | 7.0 | 84% | 91% [87-94] | 8% | 20834 |
| pmem-8 | 0.4 | 81% | 90% [82-93] | 9% | 23172 |
| model_ifs | 7.0 | 88% | 92% [88-97] | 11% | 16386 |
| pmem-4 | 0.15 | 82% | 90% [86-92] | 11% | 24814 |
| max3 | 4.0 | 85% | 86% [75-95] | 10% | 16431 |
| desk | | 81% | 92% [84-97] | 69% | 142136 |

By month, all weeks (best rule model_ifs 6.0 vs desk): detection, events
- 202511: 83% vs desk 86%, 71 events
- 202512: 83% vs desk 88%, 145 events
- 202601: 76% vs desk 81%, 129 events
- 202602: 91% vs desk 79%, 100 events
- 202603: 93% vs desk 81%, 74 events

## Hurricane force (64 kt)

Desk, tune weeks: detection 54% of 71 events, FA area 58%, FA areas 35%, area 8308 nm2

| rule | setting | tune detection | held-out detection [90%] | held-out FA area | held-out area nm2 |
|---|---|---|---|---|---|
| max3 | 10.0 | 80% | 100% [100-100] | 51% | 1010 |
| max3 | 11.0 | 85% | 100% [100-100] | 55% | 1319 |
| pmem-4 | 0.02 | 93% | 100% [100-100] | 55% | 2767 |
| pnbr-8 | 0.15 | 86% | 100% [100-100] | 58% | 6800 |
| max3 | 12.0 | 89% | 100% [100-100] | 59% | 1745 |
| pnbr-12 | 0.3 | 86% | 100% [100-100] | 58% | 6228 |
| desk | | 54% | 67% [60-80] | 62% | 6423 |

By month, all weeks (best rule max3 10.0 vs desk): detection, events
- 202511: 73% vs desk 53%, 15 events
- 202512: 83% vs desk 62%, 29 events
- 202601: 92% vs desk 58%, 24 events
- 202602: 100% vs desk 50%, 10 events
- 202603: 62% vs desk 38%, 8 events

