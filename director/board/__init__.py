"""Director board adapters (the tracker substrate, behind a pluggable seam).

Phase 1 ships only `linear` (read), per decision D-3/RV5; a local or GitHub board
can swap in later (Phase 5) by offering the same read_issue/normalize surface.
"""
