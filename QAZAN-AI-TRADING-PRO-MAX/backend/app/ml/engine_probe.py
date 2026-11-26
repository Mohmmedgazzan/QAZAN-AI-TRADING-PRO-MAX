from importlib import metadata
from app.schemas.common import MLPackageStatus

REQUIRED_ML_PACKAGES = [
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("scikit-learn", "sklearn"),
    ("xgboost", "xgboost"),
]


def probe_ml_runtime() -> list[MLPackageStatus]:
    statuses: list[MLPackageStatus] = []
    for dist_name, module_name in REQUIRED_ML_PACKAGES:
        try:
            __import__(module_name)
            version = metadata.version(dist_name)
            statuses.append(MLPackageStatus(name=dist_name, installed=True, version=version))
        except Exception:
            statuses.append(MLPackageStatus(name=dist_name, installed=False, version=None))
    return statuses
