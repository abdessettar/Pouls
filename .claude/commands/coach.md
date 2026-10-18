---
description: Start a session with Pouls Coach (the first one is an onboarding interview)
allowed-tools: mcp__pouls-coach
---

Start a Pouls Coach session.

1. Call `get_method` and follow it for the whole session.
2. Call `get_journal`. If the profile is empty, run the onboarding from the method: ask a little at
   a time, store answers with `update_profile`, then look at `get_history`, `get_status`,
   `get_recovery` and `get_references` with me and tell the story of my activity plainly and kindly.
   End by proposing the first week's plan (through `check_plan`, then `save_plan`).
3. Otherwise greet me, say in two or three lines where things stand (the current plan, habits,
   anything new since the last export), and ask what I want to work on today.

$ARGUMENTS
