import random

# State bounding boxes          (lat_min, lat_max, lon_min, lon_max)
_STATES_BBOX = {
    #  Lower 48 only — AK & HI omitted
    "AL": (30.137, 35.008, -88.473, -84.889),
    "AZ": (31.332, 37.003, -114.816, -109.045),
    "AR": (33.006, 36.500, -94.617,  -89.644),
    "CA": (32.534, 42.009, -124.409, -114.131),
    "CO": (36.993, 41.003, -109.060, -102.041),
    "CT": (40.986, 42.050, -73.727,  -71.786),
    "DE": (38.451, 39.839, -75.789,  -75.048),
    "FL": (24.396, 31.000, -87.634,  -80.032),
    "GA": (30.356, 35.001, -85.605,  -80.840),
    "ID": (41.988, 49.001, -117.243, -111.044),
    "IL": (36.983, 42.508, -91.513,  -87.020),
    "IN": (37.771, 41.761, -88.099,  -84.784),
    "IA": (40.375, 43.501, -96.639,  -90.140),
    "KS": (36.993, 40.004, -102.051, -94.588),
    "KY": (36.497, 39.148, -89.571,  -81.964),
    "LA": (28.928, 33.020, -94.043,  -88.817),
    "ME": (42.977, 47.459, -71.085,  -66.949),
    "MD": (37.911, 39.723, -79.487,  -75.048),
    "MA": (41.187, 42.887, -73.508,  -69.927),
    "MI": (41.696, 48.306, -90.418,  -82.122),
    "MN": (43.499, 49.384, -97.239,  -89.491),
    "MS": (30.173, 34.996, -91.655,  -88.098),
    "MO": (35.998, 40.613, -95.774,  -89.099),
    "MT": (44.358, 49.001, -116.050, -104.040),
    "NE": (39.999, 43.001, -104.053, -95.309),
    "NV": (35.001, 42.000, -120.006, -114.041),
    "NH": (42.697, 45.305, -72.557,  -70.610),
    "NJ": (38.788, 41.357, -75.563,  -73.885),
    "NM": (31.333, 37.000, -109.050, -103.001),
    "NY": (40.496, 45.015, -79.763,  -71.856),
    "NC": (33.850, 36.589, -84.322,  -75.459),
    "ND": (45.937, 49.000, -104.050, -96.554),
    "OH": (38.403, 41.978, -84.820,  -80.519),
    "OK": (33.619, 37.001, -103.003, -94.431),
    "OR": (41.992, 46.293, -124.703, -116.463),
    "PA": (39.719, 42.278, -80.519,  -74.689),
    "RI": (41.146, 42.018, -71.862,  -71.120),
    "SC": (32.034, 35.215, -83.354,  -78.542),
    "SD": (42.486, 45.945, -104.057, -96.436),
    "TN": (34.983, 36.678, -90.310,  -81.646),
    "TX": (25.837, 36.500, -106.646, -93.509),
    "UT": (36.998, 42.001, -114.053, -109.041),
    "VT": (42.730, 45.017, -73.437,  -71.465),
    "VA": (36.541, 39.466, -83.675,  -75.242),
    "WA": (45.543, 49.002, -124.785, -116.915),
    "WV": (37.201, 40.638, -82.644,  -77.719),
    "WI": (42.492, 47.309, -92.889,  -86.249),
    "WY": (40.994, 45.005, -111.056, -104.052),
}

# Rough land areas in km²; sourced from 2020 Census Gazetteer
_STATES_AREA_KM2 = {
    "TX": 676587, "CA": 403466, "MT": 376962, "NM": 314917, "AZ": 294208,
    "NV": 284332, "CO": 268431, "OR": 248608, "WY": 251470, "MI": 250487,
    "MN": 206236, "UT": 212909, "ID": 213511, "KS": 211900, "NE": 198974,
    "SD": 196350, "ND": 178711, "OK": 177660, "MO": 178040, "GA": 149976,
    "IL": 143793, "IA": 144669, "NC": 139391, "FL": 138887, "WI": 140275,
    "AR": 134771, "AL": 131171, "LA": 111898, "WA": 184661, "VA": 102279,
    "TN": 106798, "PA": 115883, "OH": 105829, "NY": 122911, "ME": 79881,
    "IN": 94321,  "SC": 77858,  "WV": 62258,  "MD": 25142,  "VT": 23871,
    "NH": 23187,  "MA": 20612,  "NJ": 19049,  "CT": 12548,  "DE": 5047,
    "RI": 2679,
}

# Pre‑compute cumulative weights for fast sampling
_states, _weights = zip(*_STATES_AREA_KM2.items(), strict=True)
_cum_weights = []
running = 0
for w in _weights:
    running += w
    _cum_weights.append(running)
_TOTAL_AREA = _cum_weights[-1]


def random_us_latlon() -> tuple[float, float]:
    """
    Return a random (latitude, longitude) on land in the contiguous USA.

    Uses area‑weighted state selection plus rejection sampling.
    """
    while True:
        # 1. Pick a state ~ area
        r = random.uniform(0, _TOTAL_AREA)
        idx = next(i for i, cw in enumerate(_cum_weights) if r <= cw)
        state = _states[idx]

        lat_min, lat_max, lon_min, lon_max = _STATES_BBOX[state]

        # 2. Generate candidate
        lat = random.uniform(lat_min, lat_max)
        lon = random.uniform(lon_min, lon_max)

        # 3. Quick coarse rejection for obvious Gulf / Atlantic / Great‑Lakes spill‑overs
        #    (simple heuristic lines; good enough for casual sampling)
        if (
            # Gulf of Mexico south of 29° N
            not (lat < 29.0 and lon < -80.0)
            # Atlantic east of −67° W north of Cape Cod
            and not (lon > -67.0 and lat > 41.0)
            # Pacific west of −124° W above 40° N (off WA / OR coast)
            and not (lon < -124.0 and lat > 40.0)
        ):
            return lat, lon

