"""Small explicit contiguous-US sampler for contact creation."""

import random

# Broad inland/coastal regions avoid the ocean-heavy result of a single US box.
_REGIONS = (
    ((32.5, 41.8, -124.2, -117.0), 0.18),
    ((31.5, 48.5, -116.8, -103.0), 0.16),
    ((25.9, 36.5, -106.5, -93.6), 0.18),
    ((29.5, 42.5, -103.0, -87.0), 0.22),
    ((30.5, 41.8, -86.8, -74.5), 0.20),
    ((41.0, 46.8, -73.8, -67.2), 0.06),
)


def random_us_coordinates() -> tuple[float, float]:
    """Return approximate land coordinates in the contiguous United States."""

    lat_min, lat_max, lon_min, lon_max = random.choices(
        [region for region, _ in _REGIONS],
        weights=[weight for _, weight in _REGIONS],
        k=1,
    )[0]
    return round(random.uniform(lat_min, lat_max), 6), round(random.uniform(lon_min, lon_max), 6)
