# OSCAT-3 and STAR ASCAT against RSS ASCAT

- **Question (Jason, 2026-11-12):** "Can you build a live ASCAT/OSCAT page that could serve as verification?" Before OSCAT-3 counts as a referee, does it read like ASCAT?
- **Truth:** RSS ASCAT (Metop-B/C daily 0.25 deg maps, equivalent-neutral, as served), the referee every study uses.
- **Compared:** NOAA STAR OSCAT-3 and STAR high-res ASCAT passes, as served (no conversion), averaged into the same 0.25 deg cells.
- **Win:** none to pick; a calibration check. OSCAT-3 counts as a referee only if its bias is within ~2 kt at gale and storm force and its 34/48 kt area is within ~0.8-1.25x of ASCAT's.
- **Cases:** every day 13 Oct-7 Nov 2026 that RSS and STAR both hold (STAR keeps ~1 month). Rain-flagged cells dropped from both.
- **Data cost:** ~12 GB streamed from STAR (under the 50 GB line), cached as truth kinds `oscat` / `uhr`. Approved with the page plan ("go", 12:48Z).
