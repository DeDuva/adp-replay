"""Vendor ADP's OpenAPI document into this repository.

Two stages, deliberately separate. This one pulls ADP's `spec/openapi.yaml` and
writes it here as JSON; `generate_adp_client.py` turns that into Python. The
split is what keeps the generator dependency-free: YAML needs a parser that is
not in the standard library, and a repository whose *build* needs one is a
repository whose published artifacts cannot be re-verified on a bare Python.

Vendoring rather than fetching at build time is the same argument as pinning an
image by digest. The generated client and the document it was generated from
have to travel together, or "generated from the spec" stops being checkable the
moment ADP's main branch moves.

    python3 tools/sync_adp_spec.py --source ../adp/spec/openapi.yaml

Needs PyYAML, and only here. Nothing at runtime or in the test suite imports it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

VENDORED = Path(__file__).resolve().parents[1] / "spec" / "adp-openapi.json"


def canonical_bytes(document: Any) -> bytes:
    """Stable serialization, so the digest tracks content and not formatting."""
    return json.dumps(document, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def digest_of(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Path to ADP's openapi.yaml")
    parser.add_argument("--out", type=Path, default=VENDORED)
    args = parser.parse_args(argv)

    try:
        import yaml
    except ModuleNotFoundError:
        print(
            "PyYAML is needed to sync the spec, and only to sync it.\n"
            "  python3 -m pip install pyyaml",
            file=sys.stderr,
        )
        return 2

    document = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    payload = canonical_bytes(document)

    previous = args.out.read_bytes() if args.out.exists() else b""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)

    version = document.get("info", {}).get("version", "?")
    status = "unchanged" if payload == previous else "updated"
    print(f"{args.out.name}: {status}, ADP contract {version}, {digest_of(payload)}")
    if status == "updated":
        print("Now run: make generate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
