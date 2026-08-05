# ADP contract findings

What building the §2 client against a live ADP turned up. Recorded here rather than fixed: ADP
feature work is a non-goal of this plan (execution-plan §10), and a consumer's job is to report what
the contract does, not to change it.

Found against **ADP contract 0.1.0**, spec digest
`sha256:dcf27a36ca43a2a3063ac5b6d2280b9cdef168cd89eac62ad244cc21db05f75f`, on 2026-08-05. Each has a
test in `tests/contract/` that will start failing — loudly, and in the right direction — if ADP
fixes it.

---

## 1. `payload` is documented optional and is `NOT NULL` in the database

**Severity: this one takes a run down.**

`POST /api/adp/repos/{owner}/{repo}/sessions/{id}/events` declares `required: [kind]`. An event with
only a `kind` is therefore a legal request. It returns **500**:

```
null value in column "payload" of relation "session_events" violates not-null constraint
```

A recorder emitting an event the contract says is legal can crash its own run mid-experiment, and a
500 is not something a client can classify or retry meaningfully.

**Workaround in this repo:** `AdpClient.append_events` defaults `payload` to `{}` on any event that
omits it. It is commented as a workaround at the point it happens, not presented as modelling.

**Fix ADP should make:** either give the column a default of `'{}'::jsonb`, or make `payload`
genuinely required in the spec and return 422 when it is missing. Either is fine; the current pairing
is the only combination that is not.

**Test:** `test_an_event_without_a_payload_is_accepted`.

## 2. The append response's field names are not the ones the prose implies

The spec documents this response entirely in prose — "Appended, with the new chain head, any
duplicates that were skipped, and `accepted_through`" — with no schema. Written against that
description, this client got two of five fields wrong, and only found out against a real server.

| what the prose suggests | what ADP returns |
|---|---|
| `chain_head` | **`head`** |
| `duplicates` as a count | **a list of `client_event_id`s** |
| — | also `appended`, `count`, `session_id`, `events` |

The second is the dangerous one. `duplicates` reads as truthy-when-nonzero either way, so code that
tests `if duplicates:` behaves the same and code that does arithmetic on it breaks only once a
duplicate actually occurs — during a retry, which is exactly when the recorder is already in trouble.

**Fix ADP should make:** attach response schemas to the native-plane endpoints. This is the general
form of the problem: **requests are typed by the spec and responses are not**, so a generated client
can only ever type half the contract, and the untyped half is where a consumer's bugs live.

**Tests:** `test_an_append_returns_the_mark_a_spool_trims_against`,
`test_a_repeated_client_event_id_is_reported_as_a_duplicate`.

## 3. The native plane cannot open a run on its own

`POST /api/adp/repos/{owner}/{repo}/runs` requires `intent_id` and returns 422 when the intent does
not exist. Nothing in `/api/adp` creates an intent. Intents are created as a side effect of filing an
issue on the **compat plane** — `POST /api/v3/repos/{owner}/{repo}/issues` returns the `intent_id` it
minted.

Nothing in `/api/adp` creates a repository either; that is `POST /api/v3/user/repos`.

So a consumer told to use the native plane — which execution-plan §2 says is the recording hot path —
cannot get as far as opening a run without the GitHub-compatible plane. The two planes are described
as separable and are not, for this workflow.

This is not a bug in the sense the other two are; issues-as-intent is a deliberate design ("Every
issue is intent, from the moment it's filed"). But it is undocumented as a dependency, and a client
generated from the native plane alone will not work.

**What this repo does:** contract-test setup uses the compat plane and says why in a comment, so
nobody later reads it as a shortcut. Nothing on the recording hot path touches the compat plane.

**Fix ADP could make:** a native `POST /api/adp/repos/{owner}/{repo}/intents`, or a documented note
on the runs endpoint saying where an `intent_id` comes from.

**Fixture:** `intent_id` in `tests/contract/test_adp_contract.py`.

---

## What held up exactly as documented

Worth recording too, since it is the part this project depends on most.

- `ADP-API-Version` is served on **every** response, including 401s and 404s. The startup assertion
  runs before this client holds a token, which is the case worth catching.
- A batch skipping the emitter's numbering is rejected **whole**, with `expected_next_seq` naming the
  resume point. Task 1.4's spool replays from it rather than guessing.
- `accepted_through` is `null` for an emitter that sends no `producer_seq` — untracked, not
  incomplete. A spool must not read that as zero.
- `verify` reports `chains_ok` and `emitters_ok` as separate answers, with per-session
  `emitter_tracked` / `emitter_complete`. A chain that verifies perfectly can still be missing an
  event that never arrived, and ADP says so rather than averaging the two into one comforting
  boolean.
