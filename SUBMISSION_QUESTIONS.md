
# Submission questions

## Part A: How I worked

**Q1. AI transcripts.**
I used Copilot and ChatGPT for this whole task. The full, unedited chat export is attached: [[https://chatgpt.com/c/6b0527c6-88a8-83ee-bcf5-3bb4de213f6b]]. 

**Q2. Time.**
Started: [[date, time]]. Finished: [[date, time]]. Total: about [[4]] hours.

| Activity | Hours |
|---|---|
| Reading the brief, thread, tickets |30mins|
| Exploring the data | 30 mins |
| Deciding rules / writing DECISIONS.md |2 hrs |
| Writing or reviewing code | 2 hrs |
| Testing and checking results | 30mins |
| TICKETS.md and the reply to Pooja | 15mins |
| Recording | [[ ]] |

YES, I went over 3 hours.

**Q3. Who wrote what.**
- (a) Code: about 75% of the first draft was written by AI.
- (b) DECISIONS.md: about 95% by AI.
- (c) Ticket replies: about 80% by AI.


## Part B: My submission

**Q4. From memory: which user was hardest to get right?**
 u06 (Karthik). He says he was offline on 8 and 9 Nov, and his lessons arrive on 10 Nov, which looks the same as the honest offline users. What makes him different is that both lessons are the same video, v037, which was published on 10 Nov, after the days he claims. His phone also reported zero unsent events while six events were arriving. So I rejected both days and his streak restarted on 10 Nov.

**Q5. Where in my code?**
- (a) A lesson is assigned to a calendar day in `streaks/engine.py`, function `assign_local_day`, around line 149. It uses the user's local date from when the lesson started.
- (b) Duplicate handling is in two places. In `streaks/engine.py`, `dedupe` and `_sem_key` (around lines 27 to 45) remove events that have the same content, which also catches the old bug that gave resent events a new id. In `streaks/store.py` (around line 117), the same `event_id` sent twice is stored once and the earliest received time wins.



**Q6. One `event_id` I looked at by hand.**
 That is u06's `video_end` for v037, with a claimed time of 8 Nov 20:08 IST but received on 10 Nov 14:38 UTC. I was checking that the lesson was claimed two days before it arrived, and then I compared it with the publish date of v037 in `videos.csv` (10 Nov, 06:00 IST). The lesson did not exist yet on the day it claims. I also looked at `e_96c56fe7aa60` (u13's app open with `queue_depth=3`) to see that his phone really reported three unsent events before they arrived.

**Q7. From memory: u07's and u15's streaks, and my confidence.**


## Part C: Checking the AI's work

**Q8. Validation.**

1. I ran the test suite on my machine: `python -m unittest discover -s tests -t .` and it passed (40 tests). Evidence: the terminal output in my transcript.
2. I generated the CSV with `python -m streaks csv`. Evidence: `streaks_as_of_2026-11-15T1000IST.csv` and `tests/test_rules.py::test_golden_snapshot`, which checks all 15 streaks.
3. I started the server and opened the support page. .
4. I checked that the order events arrive in does not change the result. Evidence: `tests/test_order_independence.py`.
5. I checked what changes when the offline limit is 36 hours. Evidence: `tests/test_late_sync.py::test_36h_limit_changes_only_u03` and my recording.
6. I compared Pooja's numbers with the CSV. Evidence: the table in `TICKETS.md`.

**Q9. A suggestion I rejected or changed.**
The AI recommended starting with only one free freeze and testing it. I changed that to two free freezes, for new users only, because I wanted new users to feel safe early, and existing users keep paying. The setting is in `streaks/config.py` (`free_freeze_allowance` and `new_user_window_days`).

**Q10. Something the AI got wrong that I caught.**
The setup instructions. The AI told me the project needs only Python's standard library, but on Windows it failed with "No time zone found" because the timezone data is missing. I found this when I ran the tests. It also did not warn me that `python3` and `python` on my computer are two different installs, and only one had the fix. The fix is `requirements.txt` (`tzdata`), the friendly error in `streaks/__init__.py`, and the note in `README.md`.

**Q11. A decision I changed my mind on.**
At first I wanted to give 2 or 3 free freezes. After seeing the cost (giving them to everyone could lose up to Rs 35 to 125 lakh, but new users only cost about Rs 13 each) I changed to two free freezes for new users only.

## Part D: Self-assessment

**Q12.** 

| # | Statement | 1-5 |
|---|---|---|
| a | I read every line of code in my submission. |  3  |
| b | The AI made no mistakes on this task. | 1 |
| c | Some of my stakeholder decisions could reasonably have gone the other way. | 5 |
| d | I verified every number in DECISIONS.md myself. | 4 |
| e | There's at least one part of my submission I'm not sure is correct. | 5 |
| f | I have never shipped code I didn't fully understand. | 4 |
| g | I could rebuild the core streak logic without AI in a working day. | 4 |
| h | I'd be comfortable changing any rule in my code live, on a call, today. | 4 |

**Q13.**
- (a) Quality of the AI's work: 8/10. It found the hard cases (u06, outage, the 54 vs 55 timing), but it made some mistakes and needed testing.
- (b) Quality of my own contribution: 9/10.
- If the AI had done the task alone, it would most likely have trusted the phone's timestamp, counted opening the app as learning, and missed that u06's lesson was published after the day he claims.

**Q14. Which ticket took longest?**
T7 (u06), because the data looks the same as the honest offline users until you check the video's publish date and the phone's queue count, and the reply has to be firm without accusing him.

**Q15. Least confident part.**
The u13/u14 policy. I accept both because their phones reported the right number of unsent events, but that count is sent by the app and a determined cheater could fake it. If the share of fake claims among accepted ones turned out to be above about 30%, or accepted users started cheating in bulk, I would be wrong.

## Part E: Limits

**Q16. Why did u11's app stop on 11 Nov?**
I don't know. The data shows a `video_start` with no `video_end`, nothing waiting to sync on his next app open, and it was not during the outage. The most likely causes are that the app was killed or crashed, or he closed it and left. Because there is no proof he finished a lesson, I did not count that day.

**Q17. The weakest rule or threshold.**
The 80% completion rule and the 120-second minimum, together with the cap of 3 uncorroborated late lessons per 30 days. They are my best guesses from this small data. With real production data I would look at how long honest users actually watch, check them against audited cheating cases, and pick the numbers that keep false rejections low while still catching the swipe farmers like u04.

**Q18. Anything to flag.**
- The AI wrote most of the first draft, and I read and ran it.
- The claim that the early freeze offer recovers about two thirds of the lost freeze sales is an assumption, not data.
- The outage list uses only the four user ids from the log sample.
- The bridge for u15's skipped date and the 54 vs 55 timing for u02 are decisions I made and could argue either way.

**Q19. Declaration.**
**Partly.** I used Copilot to draft the flow of answers.
