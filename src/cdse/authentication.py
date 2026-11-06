# ---- This is <authentication.py> ----

"""Authentication utilities for Copernicus Data Space Ecosystem (CDSE)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from loguru import logger

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

__all__ = [
    "get_access_token",
    "get_access_token_from_dotenv",
    "get_user_and_password",
]

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def get_user_and_password(
    dotenv_path: str | Path = ".env",
) -> tuple[str, str]:
    """Load CDSE credentials from a dotenv file.

    The dotenv file must contain:

    .. code-block:: text

        CDSE_USER=your_username
        CDSE_PASSWORD=your_password

    Parameters
    ----------
    dotenv_path : str or pathlib.Path, optional
        Path to the dotenv file. Defaults to ``".env"``.

    Returns
    -------
    tuple[str, str]
        CDSE username and password.

    Raises
    ------
    FileNotFoundError
        If the dotenv file does not exist.
    RuntimeError
        If either required environment variable is missing or empty.
    """

    dotenv_file = Path(dotenv_path).expanduser().resolve()

    if not dotenv_file.is_file():
        raise FileNotFoundError(
            f"Could not find dotenv file: {dotenv_file}"
        )

    logger.debug("Loading CDSE credentials from {}", dotenv_file)

    # Existing environment variables are not overwritten by default.
    load_dotenv(dotenv_file)

    username = os.getenv("CDSE_USER")
    password = os.getenv("CDSE_PASSWORD")

    missing_variables = [
        variable_name
        for variable_name, value in (
            ("CDSE_USER", username),
            ("CDSE_PASSWORD", password),
        )
        if not value
    ]

    if missing_variables:
        missing = ", ".join(missing_variables)
        raise RuntimeError(
            f"Required environment variable(s) are missing or empty: {missing}"
        )

    # The check above guarantees that these are non-empty strings.
    if not isinstance(username, str) or not isinstance(password, str):
        raise RuntimeError(
            "CDSE credentials must be strings."
        )

    return username, password

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def get_access_token(
    username: str,
    password: str,
    *,
    timeout: float = 30.0,
) -> str:
    """Request an access token from CDSE.

    Parameters
    ----------
    username : str
        CDSE username.
    password : str
        CDSE password.
    timeout : float, optional
        Maximum time in seconds to wait for the request.

    Returns
    -------
    str
        CDSE access token.

    Raises
    ------
    ValueError
        If the username, password, or timeout is invalid.
    RuntimeError
        If token creation fails or the response is invalid.
    """

    if not isinstance(username, str) or not username.strip():
        raise ValueError("username must be a non-empty string.")

    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string.")

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")

    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
    }

    response: requests.Response | None = None

    try:
        response = requests.post(
            TOKEN_URL,
            data=data,
            timeout=timeout,
        )
        response.raise_for_status()
        payload: Any = response.json()

    except requests.RequestException as exc:
        if response is not None:
            response_text = response.text[:1000]
            detail = (
                f"HTTP {response.status_code}: {response_text}"
                if response_text
                else f"HTTP {response.status_code}"
            )
        else:
            detail = str(exc)

        raise RuntimeError(
            f"Access token creation failed: {detail}"
        ) from exc

    except ValueError as exc:
        raise RuntimeError(
            "Access token creation failed: response was not valid JSON."
        ) from exc

    if not isinstance(payload, Mapping):
        raise RuntimeError(
            "Access token creation failed: unexpected response format."
        )

    access_token = payload.get("access_token")

    if isinstance(access_token, str) and access_token:
        return access_token

    error_description = payload.get(
        "error_description",
        payload.get("error", "access_token is missing"),
    )

    raise RuntimeError(
        f"Access token creation failed: {error_description}"
    )

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

def get_access_token_from_dotenv(
    dotenv_path: str | Path = ".env",
    *,
    timeout: float = 30.0,
) -> str:
    """Load credentials from a dotenv file and request an access token.

    Parameters
    ----------
    dotenv_path : str or pathlib.Path, optional
        Path to the dotenv file. Defaults to ``".env"``.
    timeout : float, optional
        Maximum time in seconds to wait for the request.

    Returns
    -------
    str
        CDSE access token.
    """
    username, password = get_user_and_password(dotenv_path)

    return get_access_token(
        username,
        password,
        timeout=timeout,
    )

# -------------------------------------------------------------------------- #
# -------------------------------------------------------------------------- #

# ---- End of <authentication.py> ----
