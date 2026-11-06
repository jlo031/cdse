# ---- This is <catalogue.py> ----

"""Search the Copernicus Data Space Ecosystem catalogue."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from loguru import logger
from shapely.wkt import dumps as dump_wkt

from cdse.geometry_utils import (
    get_aoi_string_from_geojson,
    get_aoi_string_from_lat_lon_dict,
    get_product_footprint_and_center,
)

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

CATALOGUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
)

DEFAULT_TIMEOUT = 30.0

VALID_SENSORS = {"SENTINEL-1", "SENTINEL-2"}

VALID_S1_MODES = {"EW", "IW"}
VALID_S1_PRODUCT_TYPES = {"GRD", "SLC"}
VALID_S1_LEVELS = {0, 1, "0", "1"}

VALID_S2_PRODUCT_TYPES = {"1C", "2A"}
VALID_S2_LEVELS = {"1C", "2A"}

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def _configure_logging(loglevel: str) -> None:
    """Configure the Loguru logger."""
    logger.remove()
    logger.add(sys.stderr, level=loglevel)

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# -------------------------------------------------------------------------- #
# Date and time utils
# -------------------------------------------------------------------------- #

def _parse_iso_datetime(
    value: str,
    parameter_name: str,
) -> datetime:
    """Parse an ISO datetime and return a timezone-aware datetime."""
    if not isinstance(value, str):
        raise TypeError(f"{parameter_name} must be a string.")

    normalised_value = value.strip()

    if normalised_value.endswith("Z"):
        normalised_value = normalised_value[:-1] + "+00:00"

    try:
        parsed_datetime = datetime.fromisoformat(normalised_value)
    except ValueError as exc:
        raise ValueError(
            f"{parameter_name} must be an ISO datetime, for example "
            f"'2024-01-01T00:00:00Z'."
        ) from exc

    if parsed_datetime.tzinfo is None:
        parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)

    return parsed_datetime

# --------------------- #

def _format_odata_datetime(value: datetime) -> str:
    """Format a datetime for use in a CDSE OData query."""
    value = value.astimezone(timezone.utc)

    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# -------------------------------------------------------------------------- #
# Parameter checks
# -------------------------------------------------------------------------- #

def _validate_datetime_range(
    start_datetime: str,
    end_datetime: str,
) -> tuple[datetime, datetime]:
    """Validate and parse an ISO datetime range."""
    start = _parse_iso_datetime(
        start_datetime,
        "start_datetime",
    )

    end = _parse_iso_datetime(
        end_datetime,
        "end_datetime",
    )

    if start >= end:
        raise ValueError(
            "start_datetime must be earlier than end_datetime."
        )

    return start, end

# --------------------- #

def _validate_date(value: str, parameter_name: str) -> None:
    """Validate a date in YYYY-MM-DD format."""
    if not isinstance(value, str):
        raise TypeError(f"{parameter_name} must be a string.")

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{parameter_name} must use the format YYYY-MM-DD: {value!r}"
        ) from exc

# --------------------- #

def _validate_time(value: str, parameter_name: str) -> None:
    """Validate a time in HH:MM:SS format."""
    if not isinstance(value, str):
        raise TypeError(f"{parameter_name} must be a string.")

    try:
        datetime.strptime(value, "%H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            f"{parameter_name} must use the format HH:MM:SS: {value!r}"
        ) from exc

# --------------------- #

def _validate_area(area: Mapping[str, Any] | str | Path) -> None:
    """Validate a latitude/longitude mapping or GeoJSON path."""
    if isinstance(area, Mapping):
        if "lat" not in area or "lon" not in area:
            raise ValueError(
                "An area mapping must contain 'lat' and 'lon' keys."
            )

        latitude = area["lat"]
        longitude = area["lon"]

        if not isinstance(latitude, (int, float)):
            raise TypeError("Area latitude must be numeric.")

        if not isinstance(longitude, (int, float)):
            raise TypeError("Area longitude must be numeric.")

        if not -90 <= latitude <= 90:
            raise ValueError("Area latitude must be between -90 and 90.")

        if not -180 <= longitude <= 180:
            raise ValueError("Area longitude must be between -180 and 180.")

        return

    area_path = Path(area).expanduser()

    if not area_path.is_file():
        raise FileNotFoundError(
            f"Cannot find search area file: {area_path}"
        )

    if area_path.suffix.lower() not in {".json", ".geojson"}:
        raise ValueError(
            "The area file must have a .json or .geojson extension."
        )

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def _validate_cdse_request_parameters(
    sensor: str,
    area: Mapping[str, Any] | str | Path,
    start_datetime: str,
    end_datetime: str,
    sensor_mode: str | None,
    product_type: str | None,
    processing_level: str | int | None,
    max_cloud_cover: int | float,
    max_results: int,
    expand_attributes: bool,
    relative_orbit: int | None = None,
) -> tuple[datetime, datetime]:
    """Validate parameters for a CDSE catalogue request.

    The function raises an exception if any parameter is invalid. Successful
    completion means that all parameters passed validation.

    Parameters
    ----------
    sensor : str
        Sensor collection to search: ``"SENTINEL-1"`` or
        ``"SENTINEL-2"``.
    area : Mapping, str, or pathlib.Path
        A mapping containing ``"lat"`` and ``"lon"`` keys, or a path to a
        GeoJSON file.
    start_datetime : str
        Start datetime in ISO format, for example
        ``"2024-01-01T00:00:00Z"``.
    end_datetime : str
        End datetime in ISO format, for example
        ``"2024-02-01T00:00:00Z"``.
    sensor_mode : str or None
        Sentinel-1 acquisition mode, such as ``"IW"`` or ``"EW"``.
    product_type : str or None
        Product type, such as ``"GRD"``, ``"SLC"``, ``"1C"``, or ``"2A"``.
    processing_level : str, int, or None
        Product processing level.
    max_cloud_cover : int or float
        Maximum Sentinel-2 cloud-cover percentage.
    max_results : int
        Maximum number of catalogue results.
    expand_attributes : bool
        Whether to request expanded product attributes.
    relative_orbit : int or None, optional
        Sentinel-1 relative orbit number.

    Raises
    ------
    TypeError
        If a parameter has an invalid type.
    ValueError
        If a parameter has an invalid value.
    FileNotFoundError
        If the area GeoJSON file does not exist.
    """

    if not isinstance(sensor, str):
        raise TypeError("sensor must be a string.")

    sensor = sensor.upper()

    if sensor not in VALID_SENSORS:
        raise ValueError(
            f"Unsupported sensor {sensor!r}. "
            f"Valid sensors are: {sorted(VALID_SENSORS)}."
        )

    _validate_area(area)

    start, end = _validate_datetime_range(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )

    if sensor == "SENTINEL-1":
        if sensor_mode is not None:
            if not isinstance(sensor_mode, str):
                raise TypeError(
                    "sensor_mode must be a string or None."
                )

            sensor_mode = sensor_mode.upper()

            if sensor_mode not in VALID_S1_MODES:
                raise ValueError(
                    f"Invalid Sentinel-1 mode {sensor_mode!r}. "
                    f"Valid modes are: {sorted(VALID_S1_MODES)}."
                )

        if product_type is not None:
            if not isinstance(product_type, str):
                raise TypeError(
                    "product_type must be a string or None."
                )

            product_type = product_type.upper()

            if product_type not in VALID_S1_PRODUCT_TYPES:
                raise ValueError(
                    f"Invalid Sentinel-1 product type {product_type!r}. "
                    f"Valid product types are: "
                    f"{sorted(VALID_S1_PRODUCT_TYPES)}."
                )

        if processing_level is not None:
            if processing_level not in VALID_S1_LEVELS:
                raise ValueError(
                    f"Invalid Sentinel-1 processing level "
                    f"{processing_level!r}. "
                    f"Valid levels are: "
                    f"{sorted(VALID_S1_LEVELS, key=str)}."
                )

        if max_cloud_cover != 100:
            logger.warning(
                "max_cloud_cover is ignored for Sentinel-1 searches."
            )

    elif sensor == "SENTINEL-2":
        if sensor_mode is not None:
            logger.warning(
                "sensor_mode is ignored for Sentinel-2 searches."
            )

        if product_type is not None:
            if not isinstance(product_type, str):
                raise TypeError(
                    "product_type must be a string or None."
                )

            product_type = product_type.upper()

            if product_type not in VALID_S2_PRODUCT_TYPES:
                raise ValueError(
                    f"Invalid Sentinel-2 product type {product_type!r}. "
                    f"Valid product types are: "
                    f"{sorted(VALID_S2_PRODUCT_TYPES)}."
                )

        if processing_level is not None:
            if not isinstance(processing_level, str):
                raise TypeError(
                    "Sentinel-2 processing_level must be a string or None."
                )

            processing_level = processing_level.upper()

            if processing_level not in VALID_S2_LEVELS:
                raise ValueError(
                    f"Invalid Sentinel-2 processing level "
                    f"{processing_level!r}. "
                    f"Valid levels are: "
                    f"{sorted(VALID_S2_LEVELS)}."
                )

        if (
            product_type is not None
            and processing_level is not None
            and product_type != processing_level
        ):
            raise ValueError(
                "For Sentinel-2, product_type and processing_level must "
                "match if both are provided."
            )

        if isinstance(max_cloud_cover, bool):
            raise TypeError(
                "max_cloud_cover must be an int or float, not bool."
            )

        if not isinstance(max_cloud_cover, (int, float)):
            raise TypeError(
                "max_cloud_cover must be numeric."
            )

        if not 0 <= max_cloud_cover <= 100:
            raise ValueError(
                "max_cloud_cover must be between 0 and 100."
            )

    if relative_orbit is not None:
        if isinstance(relative_orbit, bool):
            raise TypeError(
                "relative_orbit must be an integer, not bool."
            )

        if not isinstance(relative_orbit, int):
            raise TypeError(
                "relative_orbit must be an integer."
            )

        if relative_orbit < 1:
            raise ValueError(
                "relative_orbit must be greater than zero."
            )

    if isinstance(max_results, bool):
        raise TypeError(
            "max_results must be an integer, not bool."
        )

    if not isinstance(max_results, int):
        raise TypeError(
            "max_results must be an integer."
        )

    if not 1 <= max_results <= 1000:
        raise ValueError(
            "max_results must be between 1 and 1000."
        )

    if not isinstance(expand_attributes, bool):
        raise TypeError(
            "expand_attributes must be a boolean."
        )

    return start, end

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# -------------------------------------------------------------------------- #
# Product queries
# -------------------------------------------------------------------------- #

def _get_product_attribute(
    product: Mapping[str, Any],
    attribute_name: str,
) -> Any:
    """Get a named expanded attribute from a CDSE product."""
    attributes = product.get("Attributes", [])

    if not isinstance(attributes, list):
        return None

    for attribute in attributes:
        if not isinstance(attribute, Mapping):
            continue

        if attribute.get("Name") == attribute_name:
            return attribute.get("Value")

    return None

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def _request_json(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Send a GET request and return a JSON object."""
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"CDSE request failed: {exc}"
        ) from exc
    except ValueError as exc:
        raise RuntimeError(
            "CDSE response was not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            "CDSE response was not a JSON object."
        )

    return payload

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def search_cdse_catalogue_by_name(
    product_name: str,
    loglevel: str = "INFO",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search the CDSE catalogue for an exact product name."""

    _configure_logging(loglevel)

    if not isinstance(product_name, str):
        raise TypeError("product_name must be a string.")

    product_name = product_name.strip()

    if not product_name:
        raise ValueError(
            "product_name must be a non-empty string."
        )

    if not product_name.endswith(".SAFE"):
        product_name += ".SAFE"

    params = {
        "$filter": f"Name eq '{product_name}'",
        "$expand": "Attributes",
    }

    logger.debug("Searching for product {}", product_name)

    response_json = _request_json(
        CATALOGUE_URL,
        params=params,
        timeout=timeout,
    )

    products = response_json.get("value", [])

    if not isinstance(products, list):
        raise RuntimeError(
            "CDSE response does not contain a valid 'value' list."
        )

    if len(products) == 1:
        logger.info("Query found exactly one product.")
    elif len(products) == 0:
        logger.warning(
            "Could not find product {}.",
            product_name,
        )
    else:
        logger.warning(
            "Query found {} products with the requested name.",
            len(products),
        )

    return response_json

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def search_cdse_s1_catalogue_by_time(
    start_datetime: str,
    end_datetime: str,
    relative_orbit: int | None = None,
    loglevel: str = "INFO",
    max_results: int = 1000,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search Sentinel-1 products by ISO datetime and relative orbit.

    Parameters
    ----------
    start_datetime : str
        Start datetime in ISO format, for example
        ``"2024-01-01T00:00:00Z"``.
    end_datetime : str
        End datetime in ISO format, for example
        ``"2024-02-01T00:00:00Z"``.
    relative_orbit : int, optional
        Sentinel-1 relative orbit number.
    loglevel : str, optional
        Loguru logging level.
    max_results : int, optional
        Maximum number of catalogue results.
    timeout : float, optional
        HTTP request timeout in seconds.

    Returns
    -------
    dict[str, Any]
        CDSE catalogue response.
    """

    _configure_logging(loglevel)

    start, end = _validate_datetime_range(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )

    if relative_orbit is not None:
        if not isinstance(relative_orbit, int):
            raise TypeError(
                "relative_orbit must be an integer."
            )

        if relative_orbit < 1:
            raise ValueError(
                "relative_orbit must be greater than zero."
            )

    if not isinstance(max_results, int):
        raise TypeError(
            "max_results must be an integer."
        )

    if not 1 <= max_results <= 1000:
        raise ValueError(
            "max_results must be between 1 and 1000."
        )

    filters = [
        "Collection/Name eq 'SENTINEL-1'",
        (
            "ContentDate/Start gt "
            f"{_format_odata_datetime(start)}"
        ),
        (
            "ContentDate/Start lt "
            f"{_format_odata_datetime(end)}"
        ),
    ]

    if relative_orbit is not None:
        filters.append(
            "Attributes/OData.CSC.IntegerAttribute/any("
            "att:att/Name eq 'relativeOrbitNumber' and "
            "att/OData.CSC.IntegerAttribute/Value eq "
            f"{relative_orbit})"
        )

    params: dict[str, Any] = {
        "$filter": " and ".join(filters),
        "$expand": "Attributes",
        "$top": max_results,
        "$orderby": "ContentDate/Start asc",
    }

    response_json = _request_json(
        CATALOGUE_URL,
        params=params,
        timeout=timeout,
    )

    products = response_json.get("value", [])

    if not isinstance(products, list):
        raise RuntimeError(
            "CDSE response does not contain a valid 'value' list."
        )

    logger.info(
        "Query found {} products.",
        len(products),
    )

    if (
        len(products) == max_results
        and "@odata.nextLink" in response_json
    ):
        logger.warning(
            "The result may contain more products. Use "
            "'@odata.nextLink' to request the next page."
        )

    return response_json

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def search_cdse_catalogue(
    sensor: str,
    area: Mapping[str, Any] | str | Path,
    start_datetime: str,
    end_datetime: str,
    sensor_mode: str | None = None,
    product_type: str | None = None,
    processing_level: str | int | None = None,
    relative_orbit: int | None = None,
    max_cloud_cover: int | float = 100,
    max_results: int = 1000,
    expand_attributes: bool = True,
    loglevel: str = "INFO",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search the CDSE catalogue for Sentinel products.

    Parameters
    ----------
    sensor : str
        ``"SENTINEL-1"`` or ``"SENTINEL-2"``.
    area : Mapping, str, or pathlib.Path
        A mapping with ``lat`` and ``lon`` keys, or a GeoJSON path.
    start_datetime : str
        Start datetime in ISO format, for example
        ``"2024-01-01T00:00:00Z"``.
    end_datetime : str
        End datetime in ISO format, for example
        ``"2024-02-01T00:00:00Z"``.
    sensor_mode : str, optional
        Sentinel-1 acquisition mode.
    product_type : str, optional
        Sentinel-1 or Sentinel-2 product type.
    processing_level : str or int, optional
        Product processing level.
    relative_orbit : int, optional
        Sentinel-1 relative orbit number.
    max_cloud_cover : int or float, optional
        Maximum Sentinel-2 cloud-cover percentage.
    max_results : int, optional
        Maximum number of catalogue results.
    expand_attributes : bool, optional
        Whether to request expanded product attributes.
    loglevel : str, optional
        Loguru logging level.
    timeout : float, optional
        HTTP request timeout in seconds.

    Returns
    -------
    dict[str, Any]
        CDSE catalogue response.
    """

    _configure_logging(loglevel)

    sensor = sensor.upper()

    start, end = _validate_cdse_request_parameters(
        sensor=sensor,
        area=area,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        sensor_mode=sensor_mode,
        product_type=product_type,
        processing_level=processing_level,
        max_cloud_cover=max_cloud_cover,
        max_results=max_results,
        expand_attributes=expand_attributes,
        relative_orbit=relative_orbit,
    )

    if isinstance(area, Mapping):
        area_wkt = get_aoi_string_from_lat_lon_dict(
            area,
            decimals=4,
        )
    else:
        area_wkt = get_aoi_string_from_geojson(
            area,
            decimals=4,
        )

    filters = [
        f"Collection/Name eq '{sensor}'",
        (
            "OData.CSC.Intersects("
            f"area=geography'SRID=4326;{area_wkt}')"
        ),
        (
            "ContentDate/Start gt "
            f"{_format_odata_datetime(start)}"
        ),
        (
            "ContentDate/Start lt "
            f"{_format_odata_datetime(end)}"
        ),
    ]

    if sensor == "SENTINEL-1":
        if sensor_mode is not None:
            sensor_mode = sensor_mode.upper()

            filters.append(
                "Attributes/OData.CSC.StringAttribute/any("
                "att:att/Name eq 'operationalMode' and "
                "att/OData.CSC.StringAttribute/Value eq "
                f"'{sensor_mode}')"
            )

        if product_type is not None:
            product_type = product_type.upper()

            filters.append(
                f"contains(Name, '{product_type}')"
            )

        if relative_orbit is not None:
            filters.append(
                "Attributes/OData.CSC.IntegerAttribute/any("
                "att:att/Name eq 'relativeOrbitNumber' and "
                "att/OData.CSC.IntegerAttribute/Value eq "
                f"{relative_orbit})"
            )

    elif sensor == "SENTINEL-2":
        if product_type is not None:
            product_type = product_type.upper()

            filters.append(
                f"contains(Name, 'MSIL{product_type}')"
            )

        if processing_level is not None:
            processing_level = str(processing_level).upper()

            filters.append(
                f"contains(Name, 'MSIL{processing_level}')"
            )

        filters.append(
            "Attributes/OData.CSC.DoubleAttribute/any("
            "att:att/Name eq 'cloudCover' and "
            "att/OData.CSC.DoubleAttribute/Value le "
            f"{max_cloud_cover})"
        )

    params: dict[str, Any] = {
        "$filter": " and ".join(filters),
        "$top": max_results,
        "$orderby": "ContentDate/Start asc",
    }

    if expand_attributes:
        params["$expand"] = "Attributes"

    logger.debug(
        "CDSE query parameters: {}",
        params,
    )

    response_json = _request_json(
        CATALOGUE_URL,
        params=params,
        timeout=timeout,
    )

    products = response_json.get("value", [])

    if not isinstance(products, list):
        raise RuntimeError(
            "CDSE response does not contain a valid 'value' list."
        )

    logger.info(
        "Query found {} products.",
        len(products),
    )

    if (
        len(products) == max_results
        and "@odata.nextLink" in response_json
    ):
        logger.warning(
            "The result may contain more products. Use "
            "'@odata.nextLink' to request the next page."
        )

    return response_json

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def find_s1_repeat_passes(
    product_name: str,
    start_datetime: str,
    end_datetime: str,
    *,
    same_mode: bool = True,
    same_product_type: bool = True,
    include_cog: bool = False,
    minimum_overlap: float = 0.95,
    include_input_product: bool = False,
    max_results: int = 1000,
    loglevel: str = "INFO",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Find Sentinel-1 repeat-pass products for an input scene.

    The input scene is identified by its exact product name. Its relative
    orbit and footprint are extracted from CDSE metadata. Candidate products
    are then searched for on the same relative orbit, within the requested
    time interval, and intersecting the input scene footprint.

    Candidates are subsequently filtered by footprint overlap to remove
    adjacent scenes from the same relative orbit.

    Parameters
    ----------
    product_name : str
        Exact Sentinel-1 product name, with or without the ``.SAFE`` suffix.
    start_datetime : str
        Start of the search interval as an ISO datetime, for example
        ``"2024-01-01T00:00:00Z"``.
    end_datetime : str
        End of the search interval as an ISO datetime, for example
        ``"2024-03-01T00:00:00Z"``.
    same_mode : bool, optional
        If ``True``, restrict results to the same acquisition mode as the
        input product, such as ``IW`` or ``EW``.
    same_product_type : bool, optional
        If ``True``, restrict results to the same broad product type, such
        as ``GRD`` or ``SLC``.
    include_cog : bool, optional
        If ``True``, include Cloud-Optimized GeoTIFF products. If ``False``,
        products whose names contain ``"COG"`` are excluded.
    minimum_overlap : float, optional
        Minimum required footprint overlap as a fraction between ``0.0`` and
        ``1.0``. The default is ``0.95``.
    include_input_product : bool, optional
        If ``False``, exclude the input product from the returned results.
    max_results : int, optional
        Maximum number of products to request from the catalogue.
    loglevel : str, optional
        Loguru logging level.
    timeout : float, optional
        HTTP request timeout in seconds.

    Returns
    -------
    dict[str, Any]
        CDSE catalogue response containing matching products.

    Raises
    ------
    TypeError
        If an argument has an invalid type.
    ValueError
        If a value is invalid.
    RuntimeError
        If the input product or required metadata cannot be found.
    """

    _configure_logging(loglevel)

    # ----------------- #
    # Validate arguments.
    # ----------------- #

    if not isinstance(product_name, str):
        raise TypeError("product_name must be a string.")

    product_name = product_name.strip()

    if not product_name:
        raise ValueError(
            "product_name must be a non-empty string."
        )

    if not isinstance(same_mode, bool):
        raise TypeError("same_mode must be a boolean.")

    if not isinstance(same_product_type, bool):
        raise TypeError(
            "same_product_type must be a boolean."
        )

    if not isinstance(include_cog, bool):
        raise TypeError("include_cog must be a boolean.")

    if not isinstance(minimum_overlap, (int, float)):
        raise TypeError(
            "minimum_overlap must be numeric."
        )

    if not 0.0 <= minimum_overlap <= 1.0:
        raise ValueError(
            "minimum_overlap must be between 0.0 and 1.0."
        )

    if not isinstance(include_input_product, bool):
        raise TypeError(
            "include_input_product must be a boolean."
        )

    if not isinstance(max_results, int):
        raise TypeError(
            "max_results must be an integer."
        )

    if not 1 <= max_results <= 1000:
        raise ValueError(
            "max_results must be between 1 and 1000."
        )

    start, end = _validate_datetime_range(
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )

    # --------------------- #
    # Find the input product.
    # --------------------- #

    input_response = search_cdse_catalogue_by_name(
        product_name=product_name,
        loglevel=loglevel,
        timeout=timeout,
    )

    input_products = input_response.get("value", [])

    if not isinstance(input_products, list) or not input_products:
        raise RuntimeError(
            f"Could not find input product: {product_name}"
        )

    if len(input_products) > 1:
        logger.warning(
            "More than one product matched {!r}; using the first.",
            product_name,
        )

    input_product = input_products[0]

    if not isinstance(input_product, Mapping):
        raise RuntimeError(
            "The input product response has an unexpected format."
        )

    input_product_id = input_product.get("Id")
    input_product_name = input_product.get(
        "Name",
        product_name,
    )

    # ----------------------------------------- #
    # Extract the input product's relative orbit.
    # ----------------------------------------- #

    relative_orbit = _get_product_attribute(
        input_product,
        "relativeOrbitNumber",
    )

    if relative_orbit is None:
        raise RuntimeError(
            "The input product does not contain a "
            "'relativeOrbitNumber' attribute."
        )

    try:
        relative_orbit = int(relative_orbit)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "The input product has an invalid relative-orbit value: "
            f"{relative_orbit!r}"
        ) from exc

    # ------------------------------------ #
    # Extract the input product's footprint.
    # ------------------------------------ #

    try:
        input_geometry, _ = get_product_footprint_and_center(
            input_product,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Could not extract the input product footprint."
        ) from exc

    if input_geometry.is_empty:
        raise RuntimeError(
            "The input product footprint is empty."
        )

    if not input_geometry.is_valid:
        logger.warning(
            "The input product footprint is not valid."
        )

    if input_geometry.area <= 0:
        raise RuntimeError(
            "The input product footprint has zero area."
        )

    input_footprint_wkt = dump_wkt(
        input_geometry,
        rounding_precision=4,
    )

    # ---------------------------------------------- #
    # Extract acquisition mode and broad product type.
    # ---------------------------------------------- #

    input_name = str(input_product_name).removesuffix(".SAFE")
    name_parts = input_name.split("_")

    # Typical Sentinel-1 product name:
    #
    # S1A_IW_GRDH_1SDV_20240115T105432_...
    #
    # name_parts[1] -> IW
    # name_parts[2] -> GRDH
    input_mode = (
        name_parts[1]
        if len(name_parts) > 1
        else None
    )

    input_product_type = (
        name_parts[2][:3]
        if len(name_parts) > 2
        else None
    )

    logger.info(
        "Input product relative orbit: {}",
        relative_orbit,
    )
    logger.info(
        "Input product footprint extracted successfully."
    )

    if input_mode is not None:
        logger.info(
            "Input product acquisition mode: {}",
            input_mode,
        )

    if input_product_type is not None:
        logger.info(
            "Input product type: {}",
            input_product_type,
        )

    # ------------------------ #
    # Build the catalogue query.
    # ------------------------ #

    filters = [
        "Collection/Name eq 'SENTINEL-1'",
        (
            "ContentDate/Start ge "
            f"{_format_odata_datetime(start)}"
        ),
        (
            "ContentDate/Start le "
            f"{_format_odata_datetime(end)}"
        ),
        (
            "Attributes/OData.CSC.IntegerAttribute/any("
            "att:att/Name eq 'relativeOrbitNumber' and "
            "att/OData.CSC.IntegerAttribute/Value eq "
            f"{relative_orbit})"
        ),
        (
            "OData.CSC.Intersects("
            "area=geography'SRID=4326;"
            f"{input_footprint_wkt}')"
        ),
    ]

    if same_mode and input_mode is not None:
        filters.append(
            "Attributes/OData.CSC.StringAttribute/any("
            "att:att/Name eq 'operationalMode' and "
            "att/OData.CSC.StringAttribute/Value eq "
            f"'{input_mode}')"
        )

    if same_product_type and input_product_type is not None:
        # For example, this matches both GRDH and GRDM when the broad
        # product type is GRD.
        filters.append(
            f"contains(Name, '{input_product_type}')"
        )

    if not include_cog:
        filters.append(
            "not contains(Name, '_COG')"
        )

    params: dict[str, Any] = {
        "$filter": " and ".join(filters),
        "$expand": "Attributes",
        "$top": max_results,
        "$orderby": "ContentDate/Start asc",
    }

    logger.debug(
        "Repeat-pass query parameters: {}",
        params,
    )

    response_json = _request_json(
        CATALOGUE_URL,
        params=params,
        timeout=timeout,
    )

    products = response_json.get("value", [])

    if not isinstance(products, list):
        raise RuntimeError(
            "CDSE response does not contain a valid 'value' list."
        )

    # ------------------- #
    # Post-filter products.
    # ------------------- #

    filtered_products: list[Mapping[str, Any]] = []

    for product in products:
        if not isinstance(product, Mapping):
            logger.warning(
                "Skipping catalogue result with invalid type: {}",
                type(product).__name__,
            )
            continue

        candidate_name = product.get("Name")

        if not isinstance(candidate_name, str):
            logger.warning(
                "Skipping product without a valid 'Name' field."
            )
            continue

        if not include_cog and "COG" in candidate_name.upper():
            logger.debug(
                "Skipping COG product: {}",
                candidate_name,
            )
            continue

        if (
            not include_input_product
            and input_product_id is not None
            and product.get("Id") == input_product_id
        ):
            continue

        try:
            candidate_geometry, _ = (
                get_product_footprint_and_center(product)
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Skipping product with invalid footprint: {}",
                exc,
            )
            continue

        if candidate_geometry.is_empty:
            logger.warning(
                "Skipping product with an empty footprint: {}",
                candidate_name,
            )
            continue

        if candidate_geometry.area <= 0:
            logger.warning(
                "Skipping zero-area product footprint: {}",
                candidate_name,
            )
            continue

        try:
            intersection = input_geometry.intersection(
                candidate_geometry,
            )
        except Exception as exc:
            logger.warning(
                "Could not compare footprint for product {}: {}",
                candidate_name,
                exc,
            )
            continue

        intersection_area = intersection.area

        input_overlap = (
            intersection_area / input_geometry.area
        )

        candidate_overlap = (
            intersection_area / candidate_geometry.area
        )

        # Require the overlap threshold for both geometries. This avoids
        # accepting a large neighbouring scene that merely contains most
        # of the input scene.
        if (
            input_overlap >= minimum_overlap
            and candidate_overlap >= minimum_overlap
        ):
            filtered_products.append(product)

    response_json["value"] = filtered_products

    logger.info(
        "Found {} Sentinel-1 repeat-pass products after "
        "footprint and COG filtering.",
        len(filtered_products),
    )

    if (
        len(products) == max_results
        and "@odata.nextLink" in response_json
    ):
        logger.warning(
            "The result may contain more products. Use "
            "'@odata.nextLink' to retrieve the next page."
        )

    return response_json

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# ---- End of <catalogue.py> ----
