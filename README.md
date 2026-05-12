# Warmy Templates MCP Server

MCP server that exposes Warmy's user template API to Claude.
Covers all 8 template endpoints — create, read, list, update, delete, and statistics.

---

## Quick install via Smithery

[![Install with Smithery](https://smithery.ai/badge/@warmy/warmy-mcp)](https://smithery.ai/server/@warmy/warmy-mcp)

```bash
npx -y @smithery/cli install @warmy/warmy-mcp --client claude
```

You'll be prompted for your **Warmy API token** (find it in your Warmy account under Settings → API). That's the only credential you need.

---

## Manual setup (local dev)

1. Copy `.env.example` to `.env` and fill in your API token:
   ```
   WARMY_API_TOKEN=your_bearer_token
   ```
2. Install dependencies:
   ```bash
   venv/bin/pip install -r requirements.txt
   ```
3. Run the server:
   ```bash
   venv/bin/python main.py
   ```

---

## Tools

### `list_user_templates()`
Returns a lightweight list — **ID, name, subject only**. Fastest way to browse templates or find an ID before calling other tools. Supports filtering by name, subject, appearance, and moderation state.

**Use this first** when you don't know the template ID yet.

---

### `get_user_templates()`
Returns the **full template objects** with all fields: subject, body, appearance, warming status, moderation state, language, timestamps. Same filters as `list_user_templates()`, plus `filter_ab_test_eligible`.

**Use instead of `list_user_templates()`** when you need the body content or metadata.

---

### `get_user_template(template_id)`
Returns **complete details for one template** by ID. Use after `list_user_templates()` to get the full content of a specific template.

---

### `create_user_template(subject, body, language_code, ...)`
Creates a new template. Required fields: `subject`, `body`, `language_code`.
- Body must contain `{{ Recipient_Name }}` for text templates.
- Pass `mailbox_ids` to assign mailboxes — this automatically activates warmup.

**After creation**, call `get_user_template(id)` to see all system-generated fields.

---

### `update_user_template(template_id, ...)`
Updates an existing template. **Only include the fields you want to change** — omitted fields keep their current values. Set `run_moderation=True` to get AI moderation results synchronously.

**Before updating**, call `get_user_template(template_id)` to review current values.
**After updating**, call `get_user_templates_stats()` to monitor performance impact.

---

### `delete_user_template(template_id)`
Permanently deletes a template. Cannot be undone.

**Before deleting**, call `get_user_templates_stats()` if you want to record performance data first.

---

### `get_user_templates_stats()`
Returns templates with **per-template performance metrics**: sent count, reply rate, deliverability score. Same filters as the list endpoints.

**Use this to compare templates** and identify which ones need improvement. Take note of `template_ids` from the results and pass them to `get_user_templates_statistics()` for deeper analysis.

---

### `get_domain_providers(domain, date?)`
Returns inbox/spam delivery reports for a domain broken down by email provider.
Shows how emails perform across Gmail, Outlook, Yahoo, etc. — inbox vs spam counts and ratios.

Two sets of metrics per provider:
- `w_*` — Warmy-measured: `w_inbox`, `w_spam`, `w_spam_ratio`
- `pc_*` — provider-reported: `pc_inbox`, `pc_spam`, `pc_promotions`, `pc_spam_ratio`

`date` is optional (YYYY-MM-DD) — omit for latest data.

**Use this to identify which provider is causing issues**, then pass that provider to `get_user_templates_statistics(providers=[...])` to correlate with specific templates.

---

### `get_user_templates_statistics()`
Returns **aggregated metrics with time series** and per-provider breakdowns. More detailed than `get_user_templates_stats()`.

- `types`: `"total"` for aggregated, `"by_providers"` for per-provider (e.g. gmail, outlook)
- `period`: `"today"`, `"yesterday"`, `"week"`, `"month"` — or use `start_date`/`end_date`
- `template_ids`: filter to specific templates (get IDs from `get_user_templates_stats()`)
- `providers`: filter by provider code — `"gmail"`, `"outlook"`, `"yahoo"`, `"zoho"`, etc.

**Use this for trend analysis** or to diagnose which email provider is causing issues.

---

---

## Deliverability Checker Tools

### `list_deliverability_checkers(mailbox_id, page?, per_page?)`
Lists past deliverability test runs for a mailbox — title, token, date, and summary stats.
Use this to browse test history or find a `uniq_token` for `get_deliverability_checker()`. Max 25 per page.

---

### `create_deliverability_checker(mailbox_id, user_template_id, providers?)`
Runs a new deliverability test from a mailbox using a specific template.
Pass specific providers (`GOOGLE`, `YAHOO`, `OUTLOOK`, `ZOHO`, `GSUITE`, `ZOHOPRO`, `OUTLOOKBUSINESS`, `OTHER`) or omit for all.
Returns a `uniq_token` — pass it to `get_deliverability_checker()` to fetch results.

---

### `get_deliverability_checker(mailbox_id, uniq_token)`
Returns full results for a test run: inbox placement per provider, SPF/DKIM/DMARC checks, IP reputation, blacklist status, and overall stats.

**Use `list_deliverability_checkers()` first** to find the `uniq_token`.

---

### `toggle_auto_checker(mailbox_id, active, ...)`
Enables or disables automatic scheduled deliverability checks for one mailbox.
Optionally set `user_template_id`, `next_check_date` (YYYY-MM-DD), and `providers`.

**Use `mass_update_auto_checker()` instead** when updating multiple mailboxes at once.

---

### `mass_update_auto_checker(active, mailbox_ids?, user_template_id?)`
Applies auto-checker settings to multiple mailboxes in one call.
Omit `mailbox_ids` or pass empty list to apply to **all mailboxes** in the account.

---

## Tool Relationships

```
list_user_templates()              ← start here to browse / find IDs
        │
        ├──► get_user_template(id)          ← full content for one template
        │
        ├──► update_user_template(id, ...)  ← edit a template
        │
        └──► delete_user_template(id)       ← remove a template

create_user_template(...)          ← creates new, returns ID
        └──► get_user_template(id)          ← confirm created fields

get_user_templates_stats()         ← per-template performance overview
        └──► get_user_templates_statistics(template_ids=[...])
                                            ← time series + provider breakdown
```



