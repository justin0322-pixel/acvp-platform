"""A starting catalogue of vendors, modules and operating environments.

In a real deployment these are not server-owned: the vendor registers them with
POST /vendors, /modules, /oes (spec 12.8-12.12) and the authority approves them.
The prototype seeds a small catalogue so that the certify flow has real resources
to bind to on a fresh server — certification refuses references that do not
resolve, and an empty catalogue would mean nothing could ever be certified.

Disable with SEED_DEMO_METADATA=false.
"""
from app.core.config import get_settings
from app.store import store

_VENDOR = {"name": "NCCU ACVP demo vendor", "website": "www.example.invalid"}

_MODULES = [
    {"name": "System.Security.Cryptography.MLKem (FIPS 203)", "version": "1.0",
     "type": "software", "description": "In-box .NET 10 ML-KEM"},
    {"name": "QuantumShield ML-DSA (.NET 10)", "version": "2.1",
     "type": "software", "description": "ML-DSA signature module"},
    {"name": "PostQuantum Crypto-Suite", "version": "10.0",
     "type": "software", "description": "Combined ML-KEM / ML-DSA suite"},
]

_OES = [
    {"name": "Windows 11 (x64) AMD Ryzen 9"},
    {"name": "Ubuntu 24.04 LTS (x86_64) Intel Xeon"},
    {"name": "macOS Sequoia 15.0 (ARM64) Apple M3"},
]


def seed_demo_metadata() -> None:
    if not get_settings().seed_demo_metadata:
        return
    if store.list_metadata("modules"):
        return  # already seeded

    vendor_id = store.add_metadata("vendors", {**_VENDOR, "addresses": []})
    vendor_url = f"/acvp/v1/vendors/{vendor_id}"
    for module in _MODULES:
        store.add_metadata("modules", {**module, "vendorUrl": vendor_url})
    for oe in _OES:
        store.add_metadata("oes", {**oe, "dependencyUrls": []})
