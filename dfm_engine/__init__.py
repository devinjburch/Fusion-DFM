"""CAD-independent DFM rules engine. Must not import Fusion (adsk) modules."""
from .models import (GeometryRef, Hole, Bend, Flange, PartModel, Status, Severity,
                     RuleResult, Report)
from .profile import load_profile, load_profile_dict, list_profiles, ProfileError
from .engine import evaluate
from .models import Cutout
from .corrections import Correction

__version__ = "0.2.0"

__all__ = ["Cutout", "Correction", "__version__", "GeometryRef", "Hole", "Bend", "Flange", "PartModel", "Status", "Severity",
           "RuleResult", "Report", "load_profile", "load_profile_dict", "list_profiles",
           "ProfileError", "evaluate"]
