"""Shared test helpers for driving the result-submission flow."""
import json

from app.core.config import get_settings


def golden_response(vs_id: int, mode_folder: str = "ML-KEM-keyGen-FIPS203") -> dict:
    """A valid client submission: the NIST golden answers, stamped with our vsId."""
    path = get_settings().fixtures_dir / mode_folder / "expectedResults.json"
    expected = json.loads(path.read_text())
    return {**expected, "vsId": vs_id}


def registration(mode_folder: str = "ML-KEM-keyGen-FIPS203") -> dict:
    """A valid capability registration: the NIST example for this mode."""
    path = get_settings().fixtures_dir / mode_folder / "registration.json"
    return json.loads(path.read_text())
