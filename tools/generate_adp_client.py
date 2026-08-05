"""Generate the ADP wire surface from the vendored OpenAPI document.

Execution-plan §2: "Generate the client from ADP's spec/openapi.yaml. Do not
hand-write it." What is generated is everything the specification actually
specifies — the operations, their methods and path templates, their path
parameters, the request fields they require, the status codes they document, and
whether they need a bearer token. A hand-transcribed path is a path that drifts
silently the first time ADP renames one; a generated one changes under `make
generate` and fails `make check-generated` in CI until somebody looks.

What is deliberately *not* generated is the transport: auth, retries, error
mapping. That layer is small, it is this repository's policy rather than ADP's,
and generating it would produce something nobody would want to read.

A note on what this codegen cannot do, because it is a limitation of the
document rather than of the generator. ADP's spec documents its responses in
prose — `description: Verification result` — with no schemas attached. So
requests are typed from the spec and responses are not; the wrapper models the
handful of response shapes it depends on, and `tests/contract/` is what holds
those to the real server. That is the honest division, and it is why the
contract tests are not optional decoration.

    make generate          # rewrite the generated module
    make check-generated   # fail if it is stale

Standard library only. See sync_adp_spec.py for why that matters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / "spec" / "adp-openapi.json"
GENERATED = ROOT / "src" / "adp_replay" / "adp" / "_generated" / "operations.py"

# The native plane is the recording hot path and the only surface this client
# consumes. The compat plane is GitHub's shape, served for `gh`, and nothing
# here should be tempted to reach for it.
INCLUDE_PREFIX = "/api/adp/"

_PATH_PARAM = re.compile(r"\{([^}]+)\}")


def operation_key(method: str, path: str) -> str:
    """A stable name for an operation, derived from what it is.

    Derived rather than taken from `operationId`, because the vendored document
    does not set one and a generator that invents names quietly is a generator
    whose output changes meaning when the spec grows.
    """
    trimmed = path.removeprefix(INCLUDE_PREFIX)
    parts: list[str] = []
    for segment in trimmed.split("/"):
        if not segment:
            continue
        matched = _PATH_PARAM.fullmatch(segment)
        # `{runId}` has to become `by_run_id`, not `by_run_d`: sanitizing before
        # snake-casing eats the capital rather than splitting on it, and the
        # resulting key reads like a typo nobody can grep for.
        parts.append(f"by_{_snake(matched.group(1))}" if matched else _snake(segment))

    stem = "_".join(parts) or "root"
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", f"{method.lower()}_{stem}")).strip("_")


def _snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def collect(document: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []

    for path, item in sorted(document.get("paths", {}).items()):
        if not path.startswith(INCLUDE_PREFIX):
            continue

        shared = [p for p in item.get("parameters", []) if isinstance(p, dict)]
        for method, spec in sorted(item.items()):
            if method not in ("get", "post", "put", "patch", "delete"):
                continue

            body = spec.get("requestBody", {}).get("content", {}).get("application/json", {})
            schema = body.get("schema", {})
            operations.append(
                {
                    "key": operation_key(method, path),
                    "method": method.upper(),
                    "path": path,
                    "path_params": _PATH_PARAM.findall(path),
                    "query_params": sorted(
                        p.get("name", "")
                        for p in spec.get("parameters", []) + shared
                        if isinstance(p, dict) and p.get("in") == "query"
                    ),
                    "required_fields": sorted(schema.get("required", [])),
                    "body_required": bool(spec.get("requestBody", {}).get("required")),
                    "statuses": sorted(spec.get("responses", {})),
                    "requires_auth": bool(spec.get("security")),
                    "summary": " ".join(spec.get("summary", "").split()),
                }
            )
    return operations


def render(document: dict[str, Any], operations: list[dict[str, Any]], digest: str) -> str:
    version = document.get("info", {}).get("version", "")
    lines = [
        '"""ADP wire surface, generated from spec/adp-openapi.json.',
        "",
        "DO NOT EDIT. Regenerate with `make generate`; `make check-generated`",
        "fails while this file disagrees with the vendored document.",
        "",
        "Only the native plane (/api/adp) is generated. The compat plane is",
        "GitHub's shape, served so that unmodified `gh` works, and is not this",
        "client's business.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final, NamedTuple",
        "",
        "",
        "class Operation(NamedTuple):",
        '    """One endpoint, exactly as the contract describes it."""',
        "",
        "    key: str",
        "    method: str",
        "    path: str",
        "    path_params: tuple[str, ...]",
        "    query_params: tuple[str, ...]",
        "    required_fields: tuple[str, ...]",
        "    body_required: bool",
        "    statuses: tuple[str, ...]",
        "    requires_auth: bool",
        "    summary: str",
        "",
        "    def url(self, base_url: str, **params: str) -> str:",
        '        """Interpolate the path template, refusing an incomplete call."""',
        "        missing = [name for name in self.path_params if name not in params]",
        "        if missing:",
        "            raise KeyError(f'{self.key} needs path parameters: {missing}')",
        "        path = self.path",
        "        for name in self.path_params:",
        "            path = path.replace('{' + name + '}', str(params[name]))",
        "        return base_url.rstrip('/') + path",
        "",
        "",
        f'SPEC_VERSION: Final = "{version}"',
        f'SPEC_DIGEST: Final = "{digest}"',
        "",
        "OPERATIONS: Final[dict[str, Operation]] = {",
    ]

    for operation in sorted(operations, key=lambda o: o["key"]):
        lines.append(f'    "{operation["key"]}": Operation(')
        lines.append(f'        key="{operation["key"]}",')
        lines.append(f'        method="{operation["method"]}",')
        lines.append(f'        path="{operation["path"]}",')
        lines.append(f"        path_params={_tuple(operation['path_params'])},")
        lines.append(f"        query_params={_tuple(operation['query_params'])},")
        lines.append(f"        required_fields={_tuple(operation['required_fields'])},")
        lines.append(f"        body_required={operation['body_required']},")
        lines.append(f"        statuses={_tuple(operation['statuses'])},")
        lines.append(f"        requires_auth={operation['requires_auth']},")
        lines.append(f"        summary={_literal(operation['summary'])},")
        lines.append("    ),")

    lines += [
        "}",
        "",
        "",
        "def operation(key: str) -> Operation:",
        '    """Look up an operation, failing loudly when the contract dropped it.',
        "",
        "    An endpoint that disappears from ADP's spec becomes an error here at",
        "    the point of use rather than a 404 in the middle of an experiment.",
        '    """',
        "    try:",
        "        return OPERATIONS[key]",
        "    except KeyError:",
        "        raise KeyError(",
        "            f'{key!r} is not in ADP contract {SPEC_VERSION}; '",
        "            'regenerate the client or stop calling it'",
        "        ) from None",
        "",
    ]
    return "\n".join(lines)


def _tuple(values: list[str]) -> str:
    if not values:
        return "()"
    inner = ", ".join(_literal(value) for value in values)
    return f"({inner},)" if len(values) == 1 else f"({inner})"


def _literal(value: str) -> str:
    return json.dumps(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=VENDORED)
    parser.add_argument("--out", type=Path, default=GENERATED)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the generated file is stale instead of rewriting it",
    )
    args = parser.parse_args(argv)

    raw = args.spec.read_bytes()
    document = json.loads(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    rendered = render(document, collect(document), digest)

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current != rendered:
            print(
                f"{args.out.relative_to(ROOT)} is stale against "
                f"{args.spec.relative_to(ROOT)}. Run: make generate",
            )
            return 1
        print(f"{args.out.relative_to(ROOT)} is current ({digest}).")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"{args.out.relative_to(ROOT)}: {len(collect(document))} operations, {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
