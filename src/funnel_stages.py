"""
Single source of truth for funnel stage string values.

Import these constants wherever Lead.current_funnel_stage or
LeadFunnelStage.stage is read, written, or compared.  Never
hardcode the stage strings inline — typos and case drift (like
the DISCOVERY vs discovery bug of Feb 2026) are caught at import
time rather than silently returning zero query results.

Ordered from earliest to latest in the customer journey:
  visits → discovery → consideration → conversion → retention
"""

VISITS = "visits"
DISCOVERY = "discovery"
CONSIDERATION = "consideration"
CONVERSION = "conversion"
RETENTION = "retention"

# Ordered list useful for stage-ordering logic
ORDERED = (VISITS, DISCOVERY, CONSIDERATION, CONVERSION, RETENTION)

# Stages that count as a "converted" lead in attribution / CAC math
CONVERSION_STAGES = (CONVERSION, RETENTION)
