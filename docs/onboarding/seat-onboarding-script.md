# Seat onboarding — the ≤15-min interview script (Track 1 / Day-0 mechanism)

> **Status: DRAFT — hypothesis until proven by a run, and the first run is YOU (seat #1).** Its done-bar
> is not "reads well" — it's: *you* complete this interview on yourself, in ≤15 min, and it produces a
> usable `twin.md` v0 **plus** a clear first-NEop pick. If it doesn't, the script is wrong, not you.
> (This is the same run-not-build discipline as everything else; the first run is the seat-#1 dogfood.)

## What this is
The first thing a new seat does. The **Interviewer NEop** runs this conversation (via Element first-contact),
and its output seeds `twin.md` v0 — enough of *how this person decides* that the Decision Shadow can start
measuring fidelity from Day 0. It also surfaces the **first useful NEop** for that seat (see
`first-neop-candidates.md`). Keep it ≤15 min: friction here is the first place adoption dies.

## Frame (say this first — ~30s)
> "This is a ~15-minute interview so your digital twin can start shadowing how you decide. No prep needed.
> The one rule: **be concrete** — a real example from this week beats any general statement. Nothing here
> is committing you to anything; you can correct the twin any time, and correcting it is what makes it good."

## The flow (timed; the §2 + §5 sections are the adoption-critical ones)

### 1. Role & scope · ~2 min
- What's your role, in one sentence?
- What kinds of decisions are *yours* to make?
- What's explicitly **not** yours — what do you hand up or sign off elsewhere?

*(Seeds: scope boundaries + the escalation map.)*

### 2. The daily grind · ~3 min  ← the first-NEop signal
- Walk me through yesterday (or a typical day). What did you do that you do **most days**?
- Of those recurring things, which do you **resent** — the ones you wish you didn't have to do?
- For the worst one: how long does it take, how many times a day/week, and what makes it annoying?

*(Seeds: the **frequency × resentment** ranking that picks the first NEop. Daily-and-resented is the target,
not impressive-but-rare. Write down the top 1–2 verbatim.)*

### 3. How you decide · ~4 min
- When you make a [their main decision type] call, what are you optimizing for?
- What will you **refuse** to do, regardless of upside? (Hard constraints / red lines.)
- Give me one **real** decision from the last week and *why* you chose that way.
- What would have changed your mind?

*(Seeds: decision-style, optimization targets, hard constraints — the core of `twin.md` v0.)*

### 4. Escalation & deference · ~2 min
- When do you push a decision *up*, and to whom?
- When do others defer to *you*?

*(Seeds: the hierarchy/escalation edges the Hierarchy Resolver needs.)*

### 5. The hand-off test · ~2 min  ← confirms the first-NEop pick
- "If a capable assistant could take **one recurring thing** off your plate starting tomorrow — something
  you do almost every day — what would you hand them **first**?"
- "What would they need to get right for you to actually trust it with that?"

*(This is the validation question. If §5's answer matches §2's top resented-daily item, you have a confirmed
first-NEop candidate. If they diverge, the §5 answer wins — it's what the person actually wants delegated.)*

### 6. Trust & kill criteria · ~1 min
- "What would make you **stop** using this?"
- "What would make you trust it more over time?"

*(Seeds: the fidelity/trust expectations + the correction loop framing.)*

## What the interview produces
| Output | From | Feeds |
|---|---|---|
| `twin.md` v0 (decision-style, optimization targets, hard constraints) | §1, §3 | Decision Shadow → fidelity Day 0 |
| Escalation map | §4 | Hierarchy Resolver |
| **First-NEop pick** (the daily-resented task) | §2 ∩ §5 | `first-neop-candidates.md` → build/wrap the first useful NEop |
| Trust + kill criteria | §6 | the correction-as-value loop; early-churn warning signs |

> The exact `twin.md` field mapping follows the twin schema (`neop-spec` / `references/neuralchat-twin.md`);
> the Interviewer NEop populates the typed fields. This script is about eliciting the *right signals* — keep
> it conversational, not a form.

## Done-bar (hold it)
- [ ] **You (seat #1) complete this on yourself, ≤15 min**, and it yields a usable `twin.md` v0.
- [ ] It surfaces a **clear, daily-resented first-NEop pick** (not a vague "would be nice").
- [ ] You'd actually hand that task to a NEop tomorrow. *(If not — the first NEop isn't useful enough yet;
      learn that from yourself, before four colleagues drift away in week two.)*

Until those boxes are checked by a real run, this is a candidate script, not the onboarding flow.
