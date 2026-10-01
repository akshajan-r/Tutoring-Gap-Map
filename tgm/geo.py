"""British National Grid (OSGB36 easting/northing) to WGS84 latitude/longitude.

GIAS publishes school locations as eastings/northings; map tools want lat/lon.
Inverse transverse Mercator on the Airy 1830 ellipsoid, then a Helmert datum
shift to WGS84 (accurate to a few metres, which is plenty for a map).
"""
from __future__ import annotations

import numpy as np

# Airy 1830 ellipsoid and National Grid projection constants
_A, _B = 6377563.396, 6356256.909
_F0 = 0.9996012717
_LAT0, _LON0 = np.radians(49.0), np.radians(-2.0)
_N0, _E0 = -100000.0, 400000.0
# WGS84 ellipsoid
_A2, _B2 = 6378137.000, 6356752.3142
# Helmert parameters OSGB36 -> WGS84
_TX, _TY, _TZ = 446.448, -125.157, 542.060
_S = -20.4894e-6
_RX, _RY, _RZ = (np.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421))


def _inverse_tm(e, n):
    e2 = 1 - _B**2 / _A**2
    nn = (_A - _B) / (_A + _B)
    lat = _LAT0 + (n - _N0) / (_A * _F0)

    def meridional_arc(lat):
        return _B * _F0 * (
            (1 + nn + 5 / 4 * nn**2 + 5 / 4 * nn**3) * (lat - _LAT0)
            - (3 * nn + 3 * nn**2 + 21 / 8 * nn**3) * np.sin(lat - _LAT0) * np.cos(lat + _LAT0)
            + (15 / 8 * nn**2 + 15 / 8 * nn**3) * np.sin(2 * (lat - _LAT0)) * np.cos(2 * (lat + _LAT0))
            - 35 / 24 * nn**3 * np.sin(3 * (lat - _LAT0)) * np.cos(3 * (lat + _LAT0))
        )

    for _ in range(10):
        m = meridional_arc(lat)
        if np.all(np.abs(n - _N0 - m) < 1e-5):
            break
        lat = lat + (n - _N0 - m) / (_A * _F0)

    sin, cos, tan = np.sin(lat), np.cos(lat), np.tan(lat)
    nu = _A * _F0 / np.sqrt(1 - e2 * sin**2)
    rho = _A * _F0 * (1 - e2) / (1 - e2 * sin**2) ** 1.5
    eta2 = nu / rho - 1
    sec = 1 / cos
    d = e - _E0
    vii = tan / (2 * rho * nu)
    viii = tan / (24 * rho * nu**3) * (5 + 3 * tan**2 + eta2 - 9 * tan**2 * eta2)
    ix = tan / (720 * rho * nu**5) * (61 + 90 * tan**2 + 45 * tan**4)
    x = sec / nu
    xi = sec / (6 * nu**3) * (nu / rho + 2 * tan**2)
    xii = sec / (120 * nu**5) * (5 + 28 * tan**2 + 24 * tan**4)
    xiia = sec / (5040 * nu**7) * (61 + 662 * tan**2 + 1320 * tan**4 + 720 * tan**6)
    lat = lat - vii * d**2 + viii * d**4 - ix * d**6
    lon = _LON0 + x * d - xi * d**3 + xii * d**5 - xiia * d**7
    return lat, lon


def _to_cartesian(lat, lon, a, b):
    e2 = 1 - b**2 / a**2
    nu = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    return (
        nu * np.cos(lat) * np.cos(lon),
        nu * np.cos(lat) * np.sin(lon),
        (1 - e2) * nu * np.sin(lat),
    )


def _from_cartesian(x, y, z, a, b):
    e2 = 1 - b**2 / a**2
    p = np.sqrt(x**2 + y**2)
    lat = np.arctan2(z, p * (1 - e2))
    for _ in range(10):
        nu = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
        lat = np.arctan2(z + e2 * nu * np.sin(lat), p)
    return lat, np.arctan2(y, x)


def bng_to_wgs84(easting, northing):
    """Vectorised conversion. Returns (lat, lon) arrays in degrees; NaN in, NaN out."""
    e = np.asarray(easting, dtype=float)
    n = np.asarray(northing, dtype=float)
    lat, lon = _inverse_tm(e, n)
    x1, y1, z1 = _to_cartesian(lat, lon, _A, _B)
    x2 = _TX + (1 + _S) * x1 - _RZ * y1 + _RY * z1
    y2 = _TY + _RZ * x1 + (1 + _S) * y1 - _RX * z1
    z2 = _TZ - _RY * x1 + _RX * y1 + (1 + _S) * z1
    lat, lon = _from_cartesian(x2, y2, z2, _A2, _B2)
    return np.degrees(lat), np.degrees(lon)
