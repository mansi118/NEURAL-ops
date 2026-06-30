# First useful NEop per seat — candidates (Track 1 adoption driver)

> **Status: CANDIDATES / HYPOTHESES — not answers to ship.** A candidate is *validated* only when the real
> seat-holder says: **"yes, I do that every day and I hate it."** That confirmation is the human's
> pain-mapping (you know your five people; I don't), not something a spec can assert. Treat each entry as a
> hypothesis to test in the interview (`seat-onboarding-script.md` §2 ∩ §5), not a build order.

## The selection criterion (the thing that decides adoption)
**Highest *frequency* of relief, not size of relief.** Adoption is built on *frequency*, not magnitude:
- An **email/inbox-triage** NEop that saves 15 min **every morning** → becomes a habit → adopted.
- A **proposal-draft** NEop that saves an hour **twice a month** → forgotten it exists by week two.

So rank candidates by **frequency × resentment**, and pick the *daily-and-resented* one — even if a rarer
task would save more time per instance. **One** genuinely-useful daily NEop first; get to ≥3/seat only after
the first earns trust.

## Prefer wrapping an existing NEop over building new
The roster already has NEops (NEURAL-ops `agents/`: `recon`, `researcher`, `proposal-writer`,
`hierarchy-resolver`, `decision-shadow`, `twin-curator`, …). When a candidate maps to one, **wrap it on the
planner→executor→verifier contract**, don't invent. New NEops only when no existing one fits the daily pain.

## Candidate first-NEops by common daily-resented knowledge-work pain
(Ordered by typical daily frequency. Match each *real* seat to the one that fits *their* grind — or to the
task they name in §5 of the interview, which overrides this table.)

| # | Candidate NEop | The daily-resented pain it hits | Freq | Maps to roster? | Day-1 done = |
|---|---|---|---|---|---|
| 1 | **Inbox/triage** | sorting + drafting replies to routine mail every morning | daily, high | new (wrap) | drafts replies to N routine threads; human approves-to-send |
| 2 | **Meeting→actions** | turning call notes into action items + owners | daily/most-days | new (wrap) | a meeting note → structured action list with owners |
| 3 | **Status/update drafting** | writing the recurring standup / status / EOD update | daily | `proposal-writer`-adjacent | a draft update from the day's activity, human edits |
| 4 | **Research brief** | "go find out X" lookups they do all day | daily–weekly | **`recon` / `researcher`** | a sourced brief on a real question they'd otherwise google |
| 5 | **Scheduling/triage** | calendar conflicts, "when can we meet" churn | daily | new (wrap) | proposes slots / resolves a real conflict, human confirms |

> These are *starting hypotheses*. The interview's §2 (daily grind) + §5 (hand-off test) tell you which one
> is real for each person — or surface a 6th you didn't list. The table is a menu to test, not a roadmap.

## The pain-mapping (YOURS — the part no spec replaces)
For each of the 5 seats, fill this from the interview (or from knowing the person):
| Seat | The task they do **every day** and **resent** | Frequency | Candidate NEop | Confirmed? |
|---|---|---|---|---|
| #1 (you) | … | … | … | run it on yourself first |
| #2–#5 | … | … | … | confirm in interview §5 |

A row is only "Confirmed" when the seat-holder says it's daily *and* resented. Unconfirmed rows are guesses
— don't build against them.

## Bars to hold (same discipline as the rest of the stack)
- **Each spec is a candidate until a real person confirms the pain is daily + real** — the spec's done-bar is
  "validated against the seat-holder's actual workflow," not "looks useful on paper."
- **Seat #1 (you) first** — if you won't use the first NEop daily for a week, it isn't useful enough yet;
  fix that before spending the other four seats' goodwill.
- **Build = wrap the chosen candidate on the planner→executor→verifier contract**, gated/proposing (not
  auto-committing) until fidelity ramps. The *first real NEop run* is T9 — box-gated + STOP-and-ask.

## What's mine vs yours
- **Mine (agent, offline):** once you name the confirmed per-seat task, spec + build/wrap that NEop.
- **Yours (human):** the pain-mapping (which daily-resented task per person) and being seat #1. I can hand
  you five good candidates; you turn them into the *right* five by knowing your team and going first.
