# ---- This is <json_utils.py> ----

"""JSON and GeoJSON file utilities for CDSE operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger
from shapely.geometry import MultiPolygon, Polygon

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# -------------------------------------------------------------------------- #
# JSON file utilities
# -------------------------------------------------------------------------- #

def write_response_dict_to_json(
    response_dict: Mapping[str, Any],
    output_file: str | Path,
) -> None:
    """Write a CDSE response dictionary to a JSON file.

    Parameters
    ----------
    response_dict : Mapping[str, Any]
        Dictionary-like CDSE response.
    output_file : str or pathlib.Path
        Destination JSON or GeoJSON file.

    Raises
    ------
    TypeError
        If ``response_dict`` is not mapping-like.
    ValueError
        If the output file does not have a ``.json`` or ``.geojson``
        extension.
    """

    if not isinstance(response_dict, Mapping):
        raise TypeError(
            "Expected response_dict to be a mapping, got "
            f"{type(response_dict).__name__}."
        )

    output_path = Path(output_file).expanduser()

    if output_path.suffix.lower() not in {".json", ".geojson"}:
        raise ValueError(
            "Output file must have a .json or .geojson extension."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(response_dict, file, indent=2)

    logger.debug("JSON response written to {}", output_path)

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def read_response_dict_from_json(
    json_path: str | Path,
) -> dict[str, Any]:
    """Read a JSON object from a file.

    Parameters
    ----------
    json_path : str or pathlib.Path
        Path to the JSON file.

    Returns
    -------
    dict[str, Any]
        Decoded JSON object.

    Raises
    ------
    FileNotFoundError
        If the JSON file does not exist.
    ValueError
        If the file does not contain a JSON object.
    """
    json_file = Path(json_path).expanduser().resolve()

    if not json_file.is_file():
        raise FileNotFoundError(f"Cannot find JSON file: {json_file}")

    with json_file.open("r", encoding="utf-8") as file:
        json_object = json.load(file)

    if not isinstance(json_object, dict):
        raise ValueError(
            f"Expected a JSON object in {json_file}, got "
            f"{type(json_object).__name__}."
        )

    return json_object

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# -------------------------------------------------------------------------- #
# GeoJSON file utilities
# -------------------------------------------------------------------------- #

def read_geojson(
    geojson_path: str | Path,
) -> dict[str, Any]:
    """Read a GeoJSON object from a file.

    Parameters
    ----------
    geojson_path : str or pathlib.Path
        Path to the GeoJSON file.

    Returns
    -------
    dict[str, Any]
        Decoded GeoJSON object.

    Raises
    ------
    FileNotFoundError
        If the GeoJSON file does not exist.
    ValueError
        If the file does not contain a JSON object.
    """

    geojson_file = Path(geojson_path).expanduser().resolve()

    if not geojson_file.is_file():
        raise FileNotFoundError(
            f"Cannot find GeoJSON file: {geojson_file}"
        )

    with geojson_file.open("r", encoding="utf-8") as file:
        geojson_object = json.load(file)

    if not isinstance(geojson_object, dict):
        raise ValueError(
            f"Expected a GeoJSON object in {geojson_file}, got "
            f"{type(geojson_object).__name__}."
        )

    return geojson_object

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def write_polygon_to_geojson(
    polygon: Polygon | MultiPolygon,
    geojson_path: str | Path,
) -> None:
    """Write a Shapely Polygon or MultiPolygon to a GeoJSON file.

    The output is a GeoJSON FeatureCollection containing one feature.

    Parameters
    ----------
    polygon : Polygon or MultiPolygon
        Shapely geometry to export.
    geojson_path : str or pathlib.Path
        Destination GeoJSON file.

    Raises
    ------
    TypeError
        If ``polygon`` is not a Polygon or MultiPolygon.
    """

    if not isinstance(polygon, (Polygon, MultiPolygon)):
        raise TypeError(
            "Expected a Shapely Polygon or MultiPolygon, got "
            f"{type(polygon).__name__}."
        )

    if isinstance(polygon, MultiPolygon):
        logger.warning(
            "Footprint is a MultiPolygon, possibly because it crosses "
            "the antimeridian."
        )

    output_path = Path(geojson_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    geojson_object = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": polygon.__geo_interface__,
                "properties": {},
            }
        ],
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(geojson_object, file, indent=2)

    logger.debug("GeoJSON file saved to {}", output_path)

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# ---- End of <json_utils.py> ----
