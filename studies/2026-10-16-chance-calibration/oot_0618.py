"""Out-of-sample check of the refit on Pacific 06/18 UTC cycles (none are in the fit's counts).

    python3 oot_0618.py [COUNTS_DIR]   (default: <RK_DATA parent>/chance-calibration/pooled_npac0618)

Steps go to the page's lead groups as the page build maps them (rk.calibrate.lead_group: 30 -> le48,
54 and 78 -> 72, 102 and 126 -> ge96). Prints Brier skill and reliability error at raw 10%+ for the page table, the raw
share and the refit, and the storm-force bins at raw 10%+.
"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1]))
import refit as F  # noqa: E402
from rk import calibrate as C  # noqa: E402
old=F.load(F.BASE)
assert not any(k.split('|')[3] in ('30','54','78','102','126') for k in old), '06/18 UTC steps already in fit counts'
new=F.load(sys.argv[1] if len(sys.argv) > 1 else F.BASE.parent / 'pooled_npac0618')
for thr in (34,48):
  for g in F.GROUPS:
    shared,_=F.table(old,'both',thr,g,'tune'); prior=C.fit_logistic(shared)
    tune,_=F.table(old,'npac',thr,g,'tune')
    P=F.PAGE[str(thr)]['npac'][g]
    c={'page':(P['raw'],P['cal']),'raw':([0,100],[0,100]),'refit':C.fit_pooled(tune,prior=prior)}
    tb=F.table(new,'npac',thr,g,'any')
    for n,(r,q) in c.items():
      s=F.scores(tb[1],r,q); print(thr,g,n,round(s['bss'],3),round(s['relerr_hi'],3),s['events'])
    if thr==48:
      R=C._rel(tb[0])
      for i in range(len(R['n'])):
        if R['n'][i]>0 and R['mean_fc'][i]>=0.1:
          m=100*R['mean_fc'][i]; print('   raw %.0f cells %d verified %.0f page %.0f refit %.0f'%(m,R['n'][i],100*R['obs_freq'][i],C.cal_at(m,*c['page']),C.cal_at(m,*c['refit'])))
