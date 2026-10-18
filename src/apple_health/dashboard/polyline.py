"""Google encoded polyline algorithm (precision 5): compact route geometry for the map."""

from __future__ import annotations


def _encode_value(v: int) -> str:
    v = ~(v << 1) if v < 0 else v << 1
    out = []
    while v >= 0x20:
        out.append(chr((0x20 | (v & 0x1F)) + 63))
        v >>= 5
    out.append(chr(v + 63))
    return "".join(out)


def encode(points: list[tuple[float, float]], precision: int = 5) -> str:
    factor = 10**precision
    out, plat, plon = [], 0, 0
    for lat, lon in points:
        ilat, ilon = round(lat * factor), round(lon * factor)
        out.append(_encode_value(ilat - plat))
        out.append(_encode_value(ilon - plon))
        plat, plon = ilat, ilon
    return "".join(out)


def decode(s: str, precision: int = 5) -> list[tuple[float, float]]:
    factor = 10**precision
    coords, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        vals = []
        for _ in range(2):
            shift, result = 0, 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        lat += vals[0]
        lon += vals[1]
        coords.append((lat / factor, lon / factor))
    return coords
