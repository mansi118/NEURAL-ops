# Phased deploy — connect backend ↔ frontend, one gate at a time

> **The rule this directory enforces: one gate per run, verify-then-STOP, never chained.** There is
> deliberately **no** single script that runs the whole integration. Each of the steps below is a separately-
> gated, STOP-AND-ASK boundary — collapsing them into one execution is the exact anti-pattern the whole plan
> exists to prevent (it would skip the box proofs and auto-cross T9). Run one gate, verify it green **on the
> live box**, then run the next. `gate-apply.sh` refuses to proceed on its own — that's the point.
>
> **PRE-REQUISITE (do this FIRST, it is not a deploy step):** scope the admin key off this box. The deploy runs
> privileged prod actions; running them from a box carrying production `AdministratorAccess` as its default
> profile is a standing exposure. Scope `mansi-synlex` to only what the deploy needs (or move admin off-box),
> **then** run these on least-privilege creds.

## The gated sequence (each its own conscious step)

| # | Gate | How | STOP-before-next check |
|---|------|-----|------------------------|
| 0 | **Scope the box** | IAM (yours) — least-privilege creds, admin off this box | — |
| 1 | **Comms tier / Synapse up** | `./gate-apply.sh "comms tier" -var 'enable_comms_tier=true' …` | Synapse **healthy** + `server_name=neuraledge.in` on the live box |
| 2 | **AS registration** | **the runbook, NOT a script** → `docs/deployment/bar1a-box-runbook.md` | backup-first · YAML-validate · restart · **Synapse came back healthy** · rollback ready |
| 3 | **Wrapper live** | `./gate-apply.sh "wrapper" -var 'enable_wrapper=true' -var 'enable_matrix_peering=true' …` | wrapper healthy + reaches palace `/mcp` + the model endpoint |
| 4 | **Bar 1a — transport** | box: `serve()`/`_cs_api_call` vs real Synapse (bar1a-box-runbook) | `echo ⟳ …` round-trips in Element = transport proven |
| 5 | **B — ranked memory** `[ML seat approval]` | `docs/deployment/box-proofs-A-B-card.md` (B1) | canary rank-1 on the oblique query, **empty=FAIL** |
| 6 | **A2 — injection resistance** | box: classifier vs the live model (bar2 runbook 1B) | full corpus routes conversational/safe |
| 7 | **GAP-2 — jail** | box: Node egress-jail contains {palace, model}, drops a third host | contained |
| 8 | **T9 — the crossing** | **conscious, separate, watching** — `wrapper_t9_ack=true` + `NEOP_T9_ACK=yes` | only when 4–7 are ALL green; approvals denied; one seat |

**Why 2 is a runbook not a script:** it's a guarded edit to a production homeserver served since April —
backup / read-current / validate / restart / health-check / rollback-inline, human-in-the-loop. A script can
*prepare* the registration file; the edit-and-verify stays your hands.

**Why 4–7 are not in a deploy script:** they are the proofs that the connection is *safe to serve*, each its
own run, verified green before the next. A deploy that jumps 3→8 skips them. They live in the box-proofs card
and the bar2 runbook, in gated order.

**Why 8 is never a script line:** T9 is the conscious authorization of the first live NEop turn, gated behind
4–7 all green. It is a deliberate keypress you make watching — not the tail of a deploy chain.

## What `gate-apply.sh` does (and refuses to do)
- **Plan-first:** runs `terraform plan` with your vars and shows it. **Refuses to apply until you type `APPLY`.**
- **One apply.** Then it **STOPS** and prints the verify-before-next reminder. It does **not** run the next gate,
  does **not** touch T9, does **not** register the AS.
- Re-run it per gate with that gate's vars. That's the whole interface: one gate, one conscious apply, stop.
