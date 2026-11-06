# ---- This is <download.py> ----

"""Download products from Copernicus Data Space Ecosystem."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from cdse.authentication import get_access_token

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

ZIPPER_URL = (
    "https://zipper.dataspace.copernicus.eu/odata/v1/Products"
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_CHUNK_SIZE = 8192

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def _download_product(
    product: Mapping[str, Any],
    download_dir: Path,
    access_token: str,
    *,
    overwrite: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Download one product using an existing access token."""
    product_name = product.get("Name")
    product_id = product.get("Id")

    if not isinstance(product_name, str) or not product_name:
        raise ValueError(
            "Product must contain a valid 'Name' field."
        )

    if not isinstance(product_id, str) or not product_id:
        raise ValueError(
            "Product must contain a valid 'Id' field."
        )

    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError(
            "chunk_size must be a positive integer."
        )

    zip_name = product_name.removesuffix(".SAFE") + ".zip"
    zip_path = download_dir / zip_name
    safe_path = download_dir / product_name

    if not overwrite and (zip_path.is_file() or safe_path.is_dir()):
        logger.info(
            "Product already exists: {}",
            product_name,
        )
        return False

    url = f"{ZIPPER_URL}({product_id})/$value"

    temporary_path = zip_path.with_suffix(".zip.part")

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    try:
        with requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=timeout,
        ) as response:
            response.raise_for_status()

            with temporary_path.open("wb") as file:
                for chunk in response.iter_content(
                    chunk_size=chunk_size,
                ):
                    if chunk:
                        file.write(chunk)

        temporary_path.replace(zip_path)

    except requests.RequestException as exc:
        temporary_path.unlink(missing_ok=True)

        raise RuntimeError(
            f"Download failed for product {product_name}: {exc}"
        ) from exc

    except OSError:
        temporary_path.unlink(missing_ok=True)
        raise

    logger.info("Downloaded product to {}", zip_path)

    return True

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def download_single_product_from_cdse(
    product: Mapping[str, Any],
    download_dir: str | Path,
    username: str,
    password: str,
    overwrite: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Download one zipped product from CDSE.

    Parameters
    ----------
    product : Mapping[str, Any]
        Product dictionary returned by a catalogue search.
    download_dir : str or pathlib.Path
        Existing destination directory.
    username : str
        CDSE username.
    password : str
        CDSE password.
    overwrite : bool, optional
        Overwrite an existing product.
    chunk_size : int, optional
        Number of bytes to read per iteration.

    Returns
    -------
    bool
        ``True`` if downloaded; ``False`` if it already existed.
    """

    if not isinstance(product, Mapping):
        raise TypeError(
            "product must be a mapping, got "
            f"{type(product).__name__}."
        )

    download_path = Path(download_dir).expanduser()

    if not download_path.is_dir():
        raise NotADirectoryError(
            f"Download directory does not exist: {download_path}"
        )

    access_token = get_access_token(
        username,
        password,
        timeout=timeout,
    )

    return _download_product(
        product,
        download_path,
        access_token,
        overwrite=overwrite,
        chunk_size=chunk_size,
        timeout=timeout,
    )

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def download_product_list_from_cdse(
    product_list: list[Mapping[str, Any]],
    download_dir: str | Path,
    username: str,
    password: str,
    overwrite: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[bool]:
    """Download a list of products from CDSE.

    Parameters
    ----------
    product_list : list[Mapping[str, Any]]
        Product dictionaries returned by a catalogue search.
    download_dir : str or pathlib.Path
        Existing destination directory.
    username : str
        CDSE username.
    password : str
        CDSE password.
    overwrite : bool, optional
        Overwrite existing products.
    chunk_size : int, optional
        Number of bytes to read per iteration.

    Returns
    -------
    list[bool]
        One result per product. ``True`` means that the product was
        downloaded; ``False`` means that it already existed.
    """

    if not isinstance(product_list, list):
        raise TypeError("product_list must be a list.")

    download_path = Path(download_dir).expanduser()

    if not download_path.is_dir():
        raise NotADirectoryError(
            f"Download directory does not exist: {download_path}"
        )

    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError(
            "chunk_size must be a positive integer."
        )

    logger.info(
        "Preparing download of {} products.",
        len(product_list),
    )

    # Request one token for the whole batch
    # rather than one token per product.
    access_token = get_access_token(
        username,
        password,
        timeout=timeout,
    )

    results: list[bool] = []

    for index, product in enumerate(product_list, start=1):
        logger.info(
            "Downloading product {} of {}.",
            index,
            len(product_list),
        )

        results.append(
            _download_product(
                product,
                download_path,
                access_token,
                overwrite=overwrite,
                chunk_size=chunk_size,
                timeout=timeout,
            )
        )

    return results

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# ---- End of <download.py> ----
