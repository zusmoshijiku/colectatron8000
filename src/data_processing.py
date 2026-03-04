"""
data_processing.py
~~~~~~~~~~~~~~~~~~
Parse volunteer availability and location capacities from CSV or Excel files.

Expected input schemas
----------------------
availability file
    volunteer : str  – unique volunteer identifier
    date      : str  – YYYY-MM-DD
    slot      : str  – time-slot label (e.g. "morning", "afternoon")
    location  : str  – street corner / collection-point identifier

capacities file
    location  : str
    date      : str
    slot      : str
    capacity  : int  – max volunteers allowed in this block

volunteer_limits file  (optional)
    volunteer : str
    min_shifts: int
    max_shifts: int
"""

from __future__ import annotations

import pathlib
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_file(path: str | pathlib.Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a DataFrame."""
    path = pathlib.Path(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"Unsupported file type: {suffix!r}. Use .csv or .xlsx/.xls.")


def _validate_columns(df: pd.DataFrame, required: list[str], source: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"File '{source}' is missing required column(s): {missing}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_availability(path: str | pathlib.Path) -> pd.DataFrame:
    """Return a tidy DataFrame of volunteer availability.

    Each row represents one (volunteer, date, slot, location) combination
    where the volunteer is available and willing to work.

    Returns
    -------
    pd.DataFrame with columns: volunteer, date, slot, location
    """
    required = ["volunteer", "date", "slot", "location"]
    df = _read_file(path)
    _validate_columns(df, required, str(path))
    df = df[required].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df = df.drop_duplicates()
    return df.reset_index(drop=True)


def load_capacities(path: str | pathlib.Path) -> pd.DataFrame:
    """Return a tidy DataFrame of location capacities.

    Each row represents one (location, date, slot) time-block with its
    maximum volunteer capacity.

    Returns
    -------
    pd.DataFrame with columns: location, date, slot, capacity
    """
    required = ["location", "date", "slot", "capacity"]
    df = _read_file(path)
    _validate_columns(df, required, str(path))
    df = df[required].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df["capacity"] = df["capacity"].astype(int)
    df = df.drop_duplicates(subset=["location", "date", "slot"])
    return df.reset_index(drop=True)


def load_volunteer_limits(
    path: str | pathlib.Path,
) -> pd.DataFrame:
    """Return per-volunteer shift limits.

    Returns
    -------
    pd.DataFrame with columns: volunteer, min_shifts, max_shifts
    """
    required = ["volunteer", "min_shifts", "max_shifts"]
    df = _read_file(path)
    _validate_columns(df, required, str(path))
    df = df[required].copy()
    df["min_shifts"] = df["min_shifts"].astype(int)
    df["max_shifts"] = df["max_shifts"].astype(int)
    return df.reset_index(drop=True)


def build_problem_data(
    availability_path: str | pathlib.Path,
    capacities_path: str | pathlib.Path,
    limits_path: Optional[str | pathlib.Path] = None,
    default_min_shifts: int = 1,
    default_max_shifts: int = 3,
) -> dict:
    """Load and combine all inputs into a single problem-data dictionary.

    Parameters
    ----------
    availability_path  : path to the availability file
    capacities_path    : path to the capacities file
    limits_path        : optional path to the per-volunteer limits file
    default_min_shifts : fallback minimum shifts per volunteer
    default_max_shifts : fallback maximum shifts per volunteer

    Returns
    -------
    dict with keys:
        availability   – pd.DataFrame (volunteer, date, slot, location)
        capacities     – pd.DataFrame (location, date, slot, capacity)
        volunteers     – sorted list of unique volunteer IDs
        blocks         – sorted list of (date, slot, location) tuples
        volunteer_min  – dict {volunteer: int}
        volunteer_max  – dict {volunteer: int}
    """
    availability = load_availability(availability_path)
    capacities = load_capacities(capacities_path)

    volunteers = sorted(availability["volunteer"].unique().tolist())

    # Build the set of (date, slot, location) blocks from availability
    blocks = sorted(
        availability[["date", "slot", "location"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )

    # Per-volunteer shift limits
    if limits_path is not None:
        limits_df = load_volunteer_limits(limits_path)
        limits_map = {
            row.volunteer: (row.min_shifts, row.max_shifts)
            for row in limits_df.itertuples(index=False)
        }
    else:
        limits_map = {}

    volunteer_min = {
        v: limits_map.get(v, (default_min_shifts, default_max_shifts))[0]
        for v in volunteers
    }
    volunteer_max = {
        v: limits_map.get(v, (default_min_shifts, default_max_shifts))[1]
        for v in volunteers
    }

    return {
        "availability": availability,
        "capacities": capacities,
        "volunteers": volunteers,
        "blocks": blocks,
        "volunteer_min": volunteer_min,
        "volunteer_max": volunteer_max,
    }
