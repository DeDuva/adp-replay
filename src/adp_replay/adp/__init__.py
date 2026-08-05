"""ADP client — a versioned REST wire contract, not a linked library.

See docs/execution-plan.md §2. The client is generated from ADP's
``spec/openapi.yaml`` into ``_generated/`` (git-ignored, regenerated, never
hand-edited); this package is the hand-written wrapper around it.

The contract is REST because ADP's implementation language may change and its
consumers are polyglot. Nothing here may assume ADP is written in any particular
language, and the recording hot path stays on REST regardless of what ADP's
GraphQL endpoint offers.
"""

from adp_replay.adp.client import AdpClient
from adp_replay.adp.version import ApiVersionMismatch, assert_api_version

__all__ = ["AdpClient", "ApiVersionMismatch", "assert_api_version"]
