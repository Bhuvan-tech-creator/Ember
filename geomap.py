"""
Aerial target-selection and finding-map utilities.

Workflow:
1. Census/Nominatim geocodes the submitted address approximately.
2. Ember returns a satellite map centered near that address.
3. User clicks the real roof in the browser.
4. The selected latitude/longitude becomes the verified property target.
5. Ember creates the final aerial finding map around the clicked point.
"""

import io
import math
import re

import requests
from PIL import Image, ImageDraw


CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
ESRI_TILE = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
HEADERS = {
    "User-Agent": "Ember-hackathon-demo/1.0 (educational use)"
}


def _normalize_address(address: str) -> str:
    return re.sub(
        r"\s+([A-Z]{2})(\s+\d{5}(-\d{4})?)?\s*$",
        r", \1\2",
        address.strip(),
    )


def _geocode_census(address: str):
    response = requests.get(
        CENSUS,
        params={
            "address": _normalize_address(address),
            "benchmark": "Public_AR_Current",
            "format": "json",
        },
        headers=HEADERS,
        timeout=25,
    )
    response.raise_for_status()

    matches = response.json()["result"]["addressMatches"]
    if not matches:
        return None

    coordinates = matches[0]["coordinates"]
    return float(coordinates["y"]), float(coordinates["x"])


def _geocode_nominatim(address: str):
    response = requests.get(
        NOMINATIM,
        params={
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": "us",
        },
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    if not data:
        return None

    return float(data[0]["lat"]), float(data[0]["lon"])


def geocode(address: str):
    for resolver in (_geocode_census, _geocode_nominatim):
        try:
            result = resolver(address)
            if result:
                return result
        except Exception:
            continue
    return None


def _tile_xy_float(latitude: float, longitude: float, zoom: int):
    n = 2 ** zoom
    latitude_radians = math.radians(latitude)

    x = (longitude + 180.0) / 360.0 * n
    y = (
        1.0
        - math.log(
            math.tan(latitude_radians)
            + 1.0 / math.cos(latitude_radians)
        )
        / math.pi
    ) / 2.0 * n

    return x, y


def _lat_lon_from_global_pixel(global_x, global_y, zoom):
    scale = 256 * (2 ** zoom)
    longitude = global_x / scale * 360.0 - 180.0

    n = math.pi - 2.0 * math.pi * global_y / scale
    latitude = math.degrees(math.atan(math.sinh(n)))

    return latitude, longitude


def _meters_per_pixel(latitude: float, zoom: int):
    return (
        156543.03392
        * math.cos(math.radians(latitude))
        / (2 ** zoom)
    )


def _fetch_satellite_canvas(latitude: float, longitude: float, zoom=19, half_tiles=1):
    """
    Downloads a 3x3 Esri World Imagery tile grid around the coordinate.

    Returns:
        {
            image: PIL Image,
            zoom: int,
            min_global_x: float,
            min_global_y: float,
            center_x: float,
            center_y: float,
            meters_per_pixel: float,
        }
    """
    x_float, y_float = _tile_xy_float(latitude, longitude, zoom)
    tile_x = int(x_float)
    tile_y = int(y_float)

    tiles_per_side = half_tiles * 2 + 1
    canvas_size = tiles_per_side * 256
    canvas = Image.new("RGB", (canvas_size, canvas_size), (240, 244, 239))

    received_tile = False

    for dx in range(-half_tiles, half_tiles + 1):
        for dy in range(-half_tiles, half_tiles + 1):
            x = tile_x + dx
            y = tile_y + dy

            try:
                response = requests.get(
                    ESRI_TILE.format(z=zoom, y=y, x=x),
                    headers=HEADERS,
                    timeout=15,
                )

                if response.status_code != 200 or len(response.content) < 1500:
                    continue

                tile = Image.open(io.BytesIO(response.content)).convert("RGB")
                canvas.paste(
                    tile,
                    ((dx + half_tiles) * 256, (dy + half_tiles) * 256),
                )
                received_tile = True

            except Exception:
                continue

    if not received_tile:
        return None

    min_global_x = (tile_x - half_tiles) * 256
    min_global_y = (tile_y - half_tiles) * 256

    center_x = x_float * 256 - min_global_x
    center_y = y_float * 256 - min_global_y

    return {
        "image": canvas,
        "zoom": zoom,
        "min_global_x": min_global_x,
        "min_global_y": min_global_y,
        "center_x": center_x,
        "center_y": center_y,
        "meters_per_pixel": _meters_per_pixel(latitude, zoom),
    }


def _draw_crosshair(image, x, y, color=(255, 255, 255)):
    drawing = ImageDraw.Draw(image)

    drawing.ellipse(
        [x - 8, y - 8, x + 8, y + 8],
        outline=color,
        width=3,
    )
    drawing.line([x - 16, y, x + 16, y], fill=color, width=2)
    drawing.line([x, y - 16, x, y + 16], fill=color, width=2)


def _draw_north_and_scale(image, meters_per_pixel):
    drawing = ImageDraw.Draw(image)
    width, height = image.size

    drawing.polygon(
        [
            (width - 34, 28),
            (width - 41, 49),
            (width - 27, 49),
        ],
        fill=(255, 255, 255),
    )
    drawing.text(
        (width - 34, 54),
        "N",
        fill=(255, 255, 255),
        anchor="mm",
    )

    bar_pixels = max(25, int(10.0 / meters_per_pixel))
    drawing.line(
        [20, height - 24, 20 + bar_pixels, height - 24],
        fill=(255, 255, 255),
        width=4,
    )
    drawing.text(
        (20, height - 44),
        "10 m",
        fill=(255, 255, 255),
    )


def preview_map_for_address(address: str):
    """
    Generates the map the user clicks to select their actual roof.

    The first crosshair is only an approximate address-geocoder estimate.
    It must not be treated as verified until the user clicks the roof.
    """
    location = geocode(address)
    if not location:
        return None

    latitude, longitude = location
    satellite = _fetch_satellite_canvas(latitude, longitude)

    if not satellite:
        return None

    image = satellite["image"].copy()
    _draw_crosshair(
        image,
        satellite["center_x"],
        satellite["center_y"],
        color=(255, 221, 87),
    )
    _draw_north_and_scale(image, satellite["meters_per_pixel"])

    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)

    return {
        "image_b64": _encode_bytes(buffer.getvalue()),
        "width": image.size[0],
        "height": image.size[1],
        "zoom": satellite["zoom"],
        "min_global_x": satellite["min_global_x"],
        "min_global_y": satellite["min_global_y"],
        "approx_lat": latitude,
        "approx_lon": longitude,
        "message": (
            "Yellow crosshair = approximate street-address result. "
            "Click your actual roof to confirm the inspection target."
        ),
    }


def pixel_to_lat_lon(preview_metadata: dict, pixel_x: float, pixel_y: float):
    global_x = preview_metadata["min_global_x"] + pixel_x
    global_y = preview_metadata["min_global_y"] + pixel_y

    return _lat_lon_from_global_pixel(
        global_x,
        global_y,
        int(preview_metadata["zoom"]),
    )


def _encode_bytes(data: bytes):
    import base64
    return base64.b64encode(data).decode("utf-8")


def _annotate_final_map(
    satellite: dict,
    findings: list,
):
    image = satellite["image"].copy()
    drawing = ImageDraw.Draw(image)

    center_x = satellite["center_x"]
    center_y = satellite["center_y"]
    meters_per_pixel = satellite["meters_per_pixel"]

    _draw_crosshair(
        image,
        center_x,
        center_y,
        color=(255, 255, 255),
    )

    radius_pixels = max(12.0 / meters_per_pixel, 28.0)
    drawing.ellipse(
        [
            center_x - radius_pixels,
            center_y - radius_pixels,
            center_x + radius_pixels,
            center_y + radius_pixels,
        ],
        outline=(255, 195, 73),
        width=3,
    )

    count = max(len(findings), 1)

    for index, _finding in enumerate(findings):
        angle = (index + 0.5) / count * 2 * math.pi - math.pi / 2
        x = center_x + radius_pixels * math.cos(angle)
        y = center_y + radius_pixels * math.sin(angle)

        marker_radius = 13
        drawing.ellipse(
            [
                x - marker_radius,
                y - marker_radius,
                x + marker_radius,
                y + marker_radius,
            ],
            fill=(193, 82, 47),
            outline=(255, 255, 255),
            width=2,
        )
        drawing.text(
            (x, y - 7),
            str(index + 1),
            fill=(255, 255, 255),
            anchor="mm",
        )

    _draw_north_and_scale(image, meters_per_pixel)

    return image


def render_final_finding_map(
    target_latitude: float,
    target_longitude: float,
    findings: list,
):
    """
    Generates the final, report-ready satellite image centered on the manually
    selected target roof. The white crosshair is the user-confirmed target.
    """
    satellite = _fetch_satellite_canvas(target_latitude, target_longitude)

    if not satellite:
        return None

    final_image = _annotate_final_map(satellite, findings)

    buffer = io.BytesIO()
    final_image.save(buffer, "JPEG", quality=90)

    return {
        "png": buffer.getvalue(),
        "mode": "satellite",
        "conceptual": False,
        "perimeter_m": 0,
        "area_m2": 0,
        "target_lat": target_latitude,
        "target_lon": target_longitude,
    }