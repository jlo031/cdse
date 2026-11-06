# ---- This is <search_utils.py> ----

"""Utilities for processing CDSE search responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def get_product_names_from_response_json(
    response_json: Mapping[str, Any],
) -> list[str]:
    """Extract product names from a CDSE search response.

    CDSE search responses commonly contain products in a top-level
    ``"value"`` field. Each product is expected to contain a ``"Name"``
    field.

    Parameters
    ----------
    response_json : Mapping[str, Any]
        CDSE search response decoded from JSON.

    Returns
    -------
    list[str]
        Product names found in the response.

    Raises
    ------
    TypeError
        If ``response_json`` is not mapping-like.
    ValueError
        If the response does not contain a valid ``"value"`` list.
    """

    if not isinstance(response_json, Mapping):
        raise TypeError(
            "Expected response_json to be a mapping, got "
            f"{type(response_json).__name__}."
        )

    product_list = response_json.get("value")

    if not isinstance(product_list, list):
        raise ValueError(
            "CDSE response must contain a 'value' field containing a list."
        )

    product_names: list[str] = []

    for product in product_list:
        if not isinstance(product, Mapping):
            logger.warning(
                "Skipping product with invalid type: {}",
                type(product).__name__,
            )
            continue

        product_name = product.get("Name")

        if not isinstance(product_name, str) or not product_name:
            logger.warning(
                "Skipping product without a valid 'Name' field."
            )
            continue

        logger.debug("Appending product name: {}", product_name)
        product_names.append(product_name)

    return product_names

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# ---- End of <credentials.py> ----
