# ---- This is <geometry_utils.py> ----

"""Geometry utilities for CDSE search and download operations."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

from geomet import wkt
from loguru import logger
from shapely.errors import ShapelyError
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.wkt import loads as load_wkt

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# -------------------------------------------------------------------------- #
# Product footprint utilities
# -------------------------------------------------------------------------- #

def get_product_footprint_and_center(
    product: Mapping[str, Any],
) -> tuple[Polygon | MultiPolygon, list[float] | list[list[float]]]:
    """Extract a product footprint and its center coordinate(s).

    For a Polygon, the center is returned as:

    ``[latitude, longitude]``

    For a MultiPolygon, one center is returned for each component as:

    ``[[latitude, longitude], ...]``

    Parameters
    ----------
    product : Mapping[str, Any]
        CDSE product dictionary containing a ``"Footprint"`` field.

    Returns
    -------
    tuple
        A Shapely Polygon or MultiPolygon and its center coordinate(s).

    Raises
    ------
    TypeError
        If ``product`` is not mapping-like.
    ValueError
        If the footprint is missing, invalid, or has an unsupported geometry
        type.
    """

    if not isinstance(product, Mapping):
        raise TypeError(
            "Expected product to be a mapping, got "
            f"{type(product).__name__}."
        )

    footprint_value = product.get("Footprint")

    if not isinstance(footprint_value, str) or not footprint_value.strip():
        raise ValueError(
            "Product does not contain a valid 'Footprint' field."
        )

    # CDSE footprints commonly look like:
    #
    # geography'SRID=4326;POLYGON ((...))'
    #
    # Split only once so that the WKT itself is preserved.
    if ";" in footprint_value:
        wkt_text = footprint_value.split(";", 1)[1]
    else:
        wkt_text = footprint_value

    wkt_text = wkt_text.strip().strip("'\"")

    try:
        geometry = load_wkt(wkt_text)
    except (ShapelyError, ValueError) as exc:
        raise ValueError(
            "Could not parse the product footprint as WKT."
        ) from exc

    logger.debug("Read product footprint: {}", geometry)

    if isinstance(geometry, Polygon):
        centroid = geometry.centroid
        center: list[float] | list[list[float]] = [
            centroid.y,
            centroid.x,
        ]
        return geometry, center

    if isinstance(geometry, MultiPolygon):
        centers = [
            [polygon.centroid.y, polygon.centroid.x]
            for polygon in geometry.geoms
        ]

        logger.debug(
            "Footprint is a MultiPolygon with {} components.",
            len(geometry.geoms),
        )

        return geometry, centers

    raise ValueError(
        "Product footprint must be a Polygon or MultiPolygon; "
        f"got {geometry.geom_type!r}."
    )


# -------------------------------------------------------------------------- #
# GeoJSON-to-WKT utilities
# -------------------------------------------------------------------------- #


def _get_geometry_from_geojson(
    geojson_object: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract a geometry from a geometry, Feature, or FeatureCollection."""

    object_type = geojson_object.get("type")

    if object_type == "Feature":
        geometry = geojson_object.get("geometry")

        if not isinstance(geometry, Mapping):
            raise ValueError("GeoJSON Feature has no valid geometry.")

        return copy.deepcopy(dict(geometry))

    if object_type == "FeatureCollection":
        features = geojson_object.get("features")

        if not isinstance(features, list):
            raise ValueError(
                "GeoJSON FeatureCollection must contain a 'features' list."
            )

        geometries: list[dict[str, Any]] = []

        for feature in features:
            if not isinstance(feature, Mapping):
                raise ValueError(
                    "Every FeatureCollection item must be an object."
                )

            geometry = feature.get("geometry")

            if not isinstance(geometry, Mapping):
                raise ValueError(
                    "Every feature must contain a valid geometry."
                )

            geometries.append(copy.deepcopy(dict(geometry)))

        return {
            "type": "GeometryCollection",
            "geometries": geometries,
        }

    if "coordinates" in geojson_object or object_type == "GeometryCollection":
        return copy.deepcopy(dict(geojson_object))

    raise ValueError(
        "Input does not appear to be a valid GeoJSON geometry, "
        "Feature, or FeatureCollection."
    )


def _ensure_2d_coordinates(coordinates: Any) -> Any:
    """Remove Z coordinates from nested GeoJSON coordinates."""

    if not isinstance(coordinates, Sequence) or isinstance(
        coordinates,
        (str, bytes),
    ):
        raise ValueError("Invalid GeoJSON coordinates.")

    if len(coordinates) == 0:
        return []

    first_value = coordinates[0]

    if isinstance(first_value, Sequence) and not isinstance(
        first_value,
        (str, bytes),
    ):
        return [
            _ensure_2d_coordinates(item)
            for item in coordinates
        ]

    if len(coordinates) < 2:
        raise ValueError(
            "A coordinate must contain at least longitude and latitude."
        )

    if not all(isinstance(value, Real) for value in coordinates[:2]):
        raise ValueError("Coordinate values must be numeric.")

    # GeoJSON coordinate order is longitude, latitude [, elevation].
    return [coordinates[0], coordinates[1]]


def _check_coordinate_bounds(coordinates: Any) -> None:
    """Validate longitude and latitude values recursively."""
    if not isinstance(coordinates, Sequence) or isinstance(
        coordinates,
        (str, bytes),
    ):
        raise ValueError("Invalid GeoJSON coordinates.")

    if len(coordinates) == 0:
        return

    first_value = coordinates[0]

    if isinstance(first_value, Sequence) and not isinstance(
        first_value,
        (str, bytes),
    ):
        for item in coordinates:
            _check_coordinate_bounds(item)
        return

    longitude, latitude = coordinates[:2]

    if not -180 <= longitude <= 180:
        raise ValueError(
            f"Longitude {longitude} is outside the valid range "
            "[-180, 180]."
        )

    if not -90 <= latitude <= 90:
        raise ValueError(
            f"Latitude {latitude} is outside the valid range [-90, 90]."
        )


def _prepare_geometry(geometry: dict[str, Any]) -> None:
    """Reduce a GeoJSON geometry to 2D and validate its coordinates."""
    geometry_type = geometry.get("type")

    if geometry_type == "GeometryCollection":
        geometries = geometry.get("geometries")

        if not isinstance(geometries, list):
            raise ValueError(
                "GeometryCollection must contain a 'geometries' list."
            )

        for child_geometry in geometries:
            if not isinstance(child_geometry, dict):
                raise ValueError(
                    "GeometryCollection contains an invalid geometry."
                )

            _prepare_geometry(child_geometry)

        return

    coordinates = geometry.get("coordinates")

    if coordinates is None:
        raise ValueError(
            "Geometry is missing its 'coordinates' field."
        )

    coordinates_2d = _ensure_2d_coordinates(coordinates)
    _check_coordinate_bounds(coordinates_2d)
    geometry["coordinates"] = coordinates_2d


def convert_geojson_obj_to_wkt(
    geojson_obj: Mapping[str, Any],
    decimals: int = 4,
) -> str:
    """Convert a GeoJSON object to Well-Known Text.

    Three-dimensional coordinates are reduced to two dimensions.
    Longitude and latitude bounds are validated.

    Parameters
    ----------
    geojson_obj : Mapping[str, Any]
        GeoJSON geometry, Feature, or FeatureCollection.
    decimals : int, optional
        Number of decimal places used in the WKT output.

    Returns
    -------
    str
        WKT representation of the geometry.

    Raises
    ------
    TypeError
        If ``geojson_obj`` is not mapping-like.
    ValueError
        If the GeoJSON object is invalid.
    """

    if not isinstance(geojson_obj, Mapping):
        raise TypeError(
            "Expected geojson_obj to be a mapping, got "
            f"{type(geojson_obj).__name__}."
        )

    if not isinstance(decimals, int) or decimals < 0:
        raise ValueError("decimals must be a non-negative integer.")

    geometry = _get_geometry_from_geojson(geojson_obj)
    _prepare_geometry(geometry)

    return wkt.dumps(geometry, decimals=decimals)


def get_aoi_string_from_geojson(
    geojson_path: str,
    decimals: int = 4,
) -> str:
    """Convert a GeoJSON file to WKT for an OpenSearch query.

    Parameters
    ----------
    geojson_path : str
        Path to the GeoJSON file.
    decimals : int, optional
        Number of decimal places used in the WKT output.

    Returns
    -------
    str
        WKT representation of the GeoJSON geometry.
    """

    # Imported here to avoid making geometry_utils responsible for the
    # implementation of JSON file reading.
    from .json_utils import read_geojson

    geojson_object = read_geojson(geojson_path)

    return convert_geojson_obj_to_wkt(
        geojson_object,
        decimals=decimals,
    )


def get_aoi_string_from_lat_lon_dict(
    lat_lon_dict: Mapping[str, Any],
    decimals: int = 4,
) -> str:
    """Convert latitude and longitude values to a WKT POINT.

    Parameters
    ----------
    lat_lon_dict : Mapping[str, Any]
        Mapping containing ``"lat"`` and ``"lon"`` values.
    decimals : int, optional
        Number of decimal places used in the WKT output.

    Returns
    -------
    str
        WKT POINT representation.

    Raises
    ------
    TypeError
        If ``lat_lon_dict`` is not mapping-like.
    ValueError
        If latitude, longitude, or required keys are invalid.
    """

    if not isinstance(lat_lon_dict, Mapping):
        raise TypeError(
            "Expected lat_lon_dict to be a mapping, got "
            f"{type(lat_lon_dict).__name__}."
        )

    if "lat" not in lat_lon_dict or "lon" not in lat_lon_dict:
        raise ValueError(
            "Input mapping must contain 'lat' and 'lon' keys."
        )

    latitude = lat_lon_dict["lat"]
    longitude = lat_lon_dict["lon"]

    if not isinstance(latitude, Real) or not isinstance(longitude, Real):
        raise ValueError("Latitude and longitude must be numeric.")

    point = {
        "type": "Point",
        "coordinates": [longitude, latitude],
    }

    aoi_string = convert_geojson_obj_to_wkt(
        point,
        decimals=decimals,
    )

    logger.debug("AOI WKT: {}", aoi_string)

    return aoi_string


# -------------------------------------------------------------------------- #
# Geometry comparison utilities
# -------------------------------------------------------------------------- #

def get_polygon_overlap(
    p1: BaseGeometry,
    p2: BaseGeometry,
) -> float:
    """Calculate the fraction of geometry 1 inside geometry 2.

    Parameters
    ----------
    p1 : shapely.geometry.base.BaseGeometry
        First geometry.
    p2 : shapely.geometry.base.BaseGeometry
        Second geometry.

    Returns
    -------
    float
        Overlap fraction between ``0.0`` and ``1.0``.

    Raises
    ------
    TypeError
        If either argument is not a Shapely geometry.
    ValueError
        If ``p1`` has zero area.
    """

    if not isinstance(p1, BaseGeometry):
        raise TypeError(
            f"p1 must be a Shapely geometry, got {type(p1).__name__}."
        )

    if not isinstance(p2, BaseGeometry):
        raise TypeError(
            f"p2 must be a Shapely geometry, got {type(p2).__name__}."
        )

    if p1.area == 0:
        raise ValueError(
            "Cannot calculate overlap because p1 has zero area."
        )

    overlap = p1.intersection(p2)
    overlap_fraction = overlap.area / p1.area

    return float(overlap_fraction)

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# ---- End of <geometry_utils.py> ----
