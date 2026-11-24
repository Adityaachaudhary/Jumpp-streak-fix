# Read me first: what is done and what is yours

**Built (AI-assisted, you must read and own it):** service, tests, support view, CSV, DECISIONS.md, TICKETS.md, scripts, README.

**Yours, by the brief's own rules - not done here on purpose:**
- `SUBMISSION_QUESTIONS.md` Q3-Q19 must be in *your* words without AI. Q1/Q3/Q19 must honestly say this work was AI-built from a transcript of this chat.
- The **5-minute recording** (see RECORDING_GUIDE.md).
- Your **start/finish times** (Q2) and the AI transcript export (Q1).
- **Read every line before the call.** You'll be asked to change a rule live. Run `python -m unittest discover -s tests -t .` and read `streaks/engine.py` top to bottom (about 400 lines).

**Judgement calls you should be able to defend (and may reverse):** 80%/120 s learning rule; accepting u13/u14 on `queue_depth`; travel date-skip bridge (u15); crediting rejected back-dated lessons at receipt time; 54 vs 55 for u02 because of the `as_of` cut-off; goodwill Freeze for u08; free freezes: first 2 free for NEW free users only (existing users pay), reminders at usual time / 21:00 / 22:30.

**Known limits:** outage protection uses only the affected-uid list (no evidence of usual watching time); premium monthly grants are not modelled (balance comes from users.csv); free-allowance "used" count is derived only from the events in the data; the "recovers 2/3 of the freeze drop" figure is an assumption, flagged as such.
