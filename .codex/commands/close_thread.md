Before marking the task as done, verify the following:

1. Code Review
- Has the code been reviewed?
- Who reviewed it?
- What issues were found and resolved?

2. QA
- Was the feature tested?
- What exactly was tested?
- Any known issues?

3. Product Review
- Was the result validated from a product perspective?
- Does it match the original intent?

4. Public Overlay Sync
- Was `make public-overlay-pull` run to pull in any upstream changes from the public `main` branch before closing?
- If there were incoming changes, were they reviewed and merged cleanly?
- Is the `sync` branch on the public remote clear — no open or unmerged PR from `sync` → `main` that includes work from this task?
- Source: `docs/private/public-overlay-sync.md`

5. Chat → Documentation
- What important decisions were made in this thread?
- Extract them explicitly.
- Where are they documented?

Rules:
- Do not assume anything
- If there is no evidence → mark as missing
- Do not accept generic answers like "done" or "reviewed"

Output format:

STATUS: PASS | BLOCKED

If BLOCKED:
- list missing items
- propose next steps