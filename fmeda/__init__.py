"""
FMEDA Calculator Package
Obliczanie wskaźników awaryjności (FIT) zgodnie z normą SN 29500 / ISO 26262.
"""

from .pipeline import FMEDAPipeline

from .fit_calculator import calculate_pi_t, calculate_lambda_real
from .failure_modes import (
    distribute_failure_modes,
    validate_failure_modes,
    DEFAULT_FAILURE_MODES,
)
from .metrics import (
    classify_fault_buckets,
    compute_metrics,
    analyse,
    FaultBuckets,
    ArchitecturalMetrics,
    SPFM_TARGETS,
    LFM_TARGETS,
)

__all__ = [
    # Moduł 1
    "calculate_pi_t",
    "calculate_lambda_real",
    # Moduł 2
    "distribute_failure_modes",
    "validate_failure_modes",
    "DEFAULT_FAILURE_MODES",
    # Moduł 3
    "classify_fault_buckets",
    "compute_metrics",
    "analyse",
    "FaultBuckets",
    "ArchitecturalMetrics",
]

