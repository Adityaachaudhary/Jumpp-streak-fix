# TICKETS.md

*(b) = what the system shows now (`/support/<user>`). Streaks are as of 15 Nov 2026 10:00 IST.*

### T1 - u02 Rahul (premium) - **54** (55 tonight)
**(a)** Moved IST -> PT on 7-8 Nov (`tz_change`). The old logic cut days in his home timezone, so 8 Nov (IST) looked empty. In his own local days he learned every day 1-14 Nov. **(b)** 14 days `LEARNED`, no gap, no freeze used (balance still 1). At 10:00 IST it is still 14 Nov in San Francisco, his lesson comes at 21:01 PT, so 54 -> 55 a few hours later. **(c)** "You're right, you didn't miss a day, and I'm sorry. Our streak cut days at India midnight instead of your local midnight after you moved. It's fixed: your streak is 54 and will be 55 when you finish today's lesson. Your Freeze is untouched." **(d)** Restore (done by recompute). Product fix: legacy day boundary uses home tz.

### T2 - u03 Ananya - **26**
**(a)** Flight lesson 10 Nov 14:05 IST synced 11 Nov 09:40 IST (19.5 h later, app 3.1.4, sent 3 copies). The "you lost your streak" push went out before the sync. **(b)** `LEARNED_LATE_UNVERIFIED` on 10 and 12 Nov (3.1.x sends no `queue_depth`); duplicates ignored. **(c)** "Sorry for the scare. You watched on the flight and it synced the next morning, so your streak is safe at 26. We shouldn't have sent that message so early, and we've changed it so you won't get one until a day is really final. Updating the app also makes offline lessons count more reliably." **(d)** None. Product: no loss push before +48 h; prompt 3.1.x users to update.

### T3 - u04 Vikram - **0**
**(a)** 6-14 Nov: he opened the app nightly and started 6-8 videos a day, each closed after 2-7 s of 75-165 s. **(b)** 25-day streak ended 6 Nov, `MISSED_SWIPE_ONLY` on 9 days. **(c)** "Thanks for telling us, and I understand the frustration. A day counts when you watch one lesson through or two minutes of lessons; on 6-14 Nov each video was closed within a few seconds, so those days didn't count. Opening the app on its own isn't enough. Watch one lesson today and a new streak starts at 1." **(d)** No restore. Ask product to check the beta build for an auto-skip bug on his device (low probability, cheap to rule out).

### T4 - u05 Meera - **20**
**(a)** Lesson started 9 Nov 23:59:05 and finished 10 Nov 00:00:27. The old logic used the end time. **(b)** 9 Nov `LEARNED` (assigned by start), 10 Nov also learned. **(c)** "You were right, you started that lesson before midnight and it counts for the 9th. Your streak is 20 and nothing is missing. Sorry for the trouble." **(d)** Restore (done). Product fix: assign by start time.

### T5 - u07 Sneha (premium) - **72**
**(a)** 7 Nov lesson watched offline in the metro, synced 8 Nov 12:00 IST (14.7 h). At 09:02 the app (not yet synced) said "missed", she bought a Freeze (Rs 49), applied to 7 Nov. Her 07:17 `app_open` already reported `queue_depth=3`, so the app could have known. **(b)** 7 Nov `LEARNED_LATE_VERIFIED`; Freeze not consumed, balance 1; refund candidate Rs 49. **(c)** "You're right, you shouldn't have had to pay. Your 7 Nov lesson synced later and counts, so the Freeze wasn't needed. I've refunded Rs 49 [or: kept it in your balance, your choice]. Your streak is 72. Sorry for the confusion." **(d)** **Refund Rs 49.** Product: never offer a Freeze while `queue_depth>0`.

### T6 - u08 Arjun (premium) - **313**
**(a)** 9 Nov 21:00 lesson lost: ingestion 503s 20:45-21:50 IST, app 3.2.0 doesn't retry; he is in the outage list. **(b)** 9 Nov `OUTAGE_PROTECTED` (bridge, adds 0), balance still 1. **(c)** "This was our fault and I'm sorry. Your 9 Nov lesson was lost in an outage, your streak is intact and has not reset. It stands at 313: protected days keep the streak alive but don't add a day, so please ignore the 314 you may have been told. As an apology we've added a free Freeze to your balance." **(d)** Goodwill Freeze (cost Rs 49 vs Rs 1,600 premium value). Alternative if Support wants to honour 314: costs nothing in money but breaks the "protected days add 0" rule used everywhere.

### T7 - u06 Karthik - **5** (40 through 7 Nov, then restarted 10 Nov)
**(a)** The two "offline" batches (8 and 9 Nov) are both lesson v037, which **was published 10 Nov 06:00 IST**, after both claimed times. Also, on reconnect his app reported `queue_depth=0` while 6 events were arriving. Not corroborated by his own device. **(b)** 8 and 9 Nov `MISSED_BACKDATE_UNPUBLISHED`; streak ended 8 Nov (no freeze); lessons credited on 10 Nov. **(c)** "Thanks for writing. We couldn't credit 8 and 9 Nov: the lesson in that sync wasn't published until the 10th, so it can't have been watched earlier. Your streak ran to 40 on 7 Nov and a new one started on the 10th (now 5). If you watched a different lesson offline, reply with your app version and I'll ask the team to look again." **(d)** No restore. Neutral tone, no accusation. T&S review only if he disputes. Pooja's holding number (47) is wrong.

### T8 - u10 Rohan - **23**
**(a)** 12 Nov: one lesson watched 101 s of 104 s (97%). The old rule wanted 2 minutes total. **(b)** 12 Nov `LEARNED`. **(c)** "You did finish it, and the 12th was wrongly grey, sorry. Our old rule needed two minutes in a day, which a short lesson can't meet. It now counts a lesson watched through. Your streak is 23." **(d)** Restore (done). Product fix: new rule.

### T9 - u13 Nikhil - **58**
**(a)** 12 Nov 20:56 lesson offline, synced 13 Nov 21:02 (24.1 h). His reconnect `app_open` said `queue_depth=3`, matching the batch of 3; lesson published 6 Oct. **(b)** 12 Nov `LEARNED_LATE_VERIFIED`. **(c)** "Good news: your offline lesson from the 12th arrived and counts. Your streak is safe at 58." **(d)** None.

### T10 - u14 Tanvi - **65**
**(a)** 11 Nov 21:31 lesson on the train, synced 12 Nov 21:24 (23.9 h), `queue_depth=3` for a batch of 3, lesson published 2 Oct. Same pattern as T9. **(b)** 11 Nov `LEARNED_LATE_VERIFIED`. **(c)** "Your lesson from the train came through and counts. Your streak is safe at 65." **(d)** None. T9 and T10 get the same treatment on the same evidence.

---

## Reply to Pooja

Hi Pooja, the CSV is `streaks_as_of_2026-11-15T1000IST.csv`. Three of the five numbers match, two need correcting before you close tickets:

| Ticket | You sent | CSV | |
|---|---|---|---|
| T1 u02 | 55 | **54** | Right, but at 10:00 IST it is still 14 Nov in San Francisco; his lesson lands at 21:01 PT. Tell him 54 now, 55 tonight. |
| T2 u03 | 26 | 26 | Matches. |
| T5 u07 | 72 | 72 | Matches. Please also refund his Rs 49. |
| T6 u08 | 314 | **313** | The outage day is protected but a protected day adds 0 (Ritika's rule, our Play Store text). Please correct the number and offer the goodwill Freeze. |
| T7 u06 | 47 | **5** | The two "offline" lessons were published after the days he claims, so they can't be credited. His streak ended 8 Nov (40) and restarted 10 Nov. Please use the neutral reply in TICKETS.md, no accusation, and send it to me if he disputes. |

Agents can open `/support/<user_id>` to see each day and what to do. Sorry about T6 and T7; I would rather correct them now than have you contradicted later.
