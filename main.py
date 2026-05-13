from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar
import asyncio
import httpx
import os
import time
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

_current_token: ContextVar[str] = ContextVar("warmy_token", default="")


class _TokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        _current_token.set(token or os.environ.get("WARMY_API_TOKEN", ""))
        return await call_next(request)

mcp = FastMCP("Warmy Templates")

BASE_URL = "https://api.warmy.io"
TIMEOUT = 30.0
HOLDER_UID = "a66a9a755fe16f24fcb99dc8b5f25a50"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_current_token.get()}",
        "Holder-Uid": HOLDER_UID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    token = _current_token.get() or os.environ.get("WARMY_API_TOKEN", "")
    if not token:
        return {"error": "Missing credentials", "detail": "WARMY_API_TOKEN is not set. Please provide your Warmy API token."}

    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.request(method, f"{BASE_URL}{path}", headers=_headers(), params=clean_params, json=json)
        if r.status_code == 401:
            return {"error": "Unauthorized", "detail": "API token or Holder-UID is invalid. Check your Warmy account settings."}
        if r.status_code == 403:
            return {"error": "Forbidden", "detail": "Your account does not have permission for this action."}
        if not r.is_success:
            return {"error": f"HTTP {r.status_code}", "detail": r.text}
        return r.json() if r.content else {"status": "success"}


# ---------------------------------------------------------------------------
# Tool 1: Get all templates (full details)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_user_templates(
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    filter_name: Optional[str] = None,
    filter_searchable: Optional[str] = None,
    filter_subject: Optional[str] = None,
    filter_appearance: Optional[str] = None,
    filter_moderation_state: Optional[str] = None,
    filter_ab_test_eligible: Optional[bool] = None,
) -> dict:
    """
    Retrieve all user templates with full details and optional filtering.

    Returns complete template objects including subject, body, appearance, warming status,
    moderation state, language, and timestamps. Use this when you need full template content.

    Use list_user_templates() instead if you only need IDs, names, and subjects — it's
    faster and returns less data.

    Parameters:
        page: Page number for pagination (default: 1).
        per_page: Results per page (default: 20).
        filter_name: Exact match on template name.
        filter_searchable: Search across both name and subject fields.
        filter_subject: Exact match on subject line.
        filter_appearance: One of "html", "text", or "hubspot".
        filter_moderation_state: One of "approved", "rejected", "pending", "no_state".
        filter_ab_test_eligible: When True, returns only templates eligible for A/B testing
            (must be warming, approved, have assignments, not a variant/copy, no active A/B test).

    Returns:
        items: List of full template objects. Each includes:
            id, name, subject, body, appearance, warming, provider,
            moderation_state, language (name + code), created_at, updated_at.
        pagination: current_page, total_pages, total_count, next_page, prev_page, limit_value.
    """
    return await _request("GET", "/api/v2/user_templates", params={
        "page": page,
        "per_page": per_page,
        "filter[name]": filter_name,
        "filter[searchable]": filter_searchable,
        "filter[subject]": filter_subject,
        "filter[appearance]": filter_appearance,
        "filter[moderation_state]": filter_moderation_state,
        "filter[ab_test_eligible]": filter_ab_test_eligible,
    })


# ---------------------------------------------------------------------------
# Tool 2: Create template
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_user_template(
    subject: str,
    body: str,
    language_code: str,
    appearance: str = "text",
    name: Optional[str] = None,
    mailbox_ids: Optional[list[int]] = None,
) -> dict:
    """
    Create a new user template.

    Rules:
    - subject: max 100 characters (required).
    - body: must contain {{ Recipient_Name }} when appearance is "text" (required).
    - language_code: ISO 639-1 format, e.g. "en", "es", "fr" (required).
    - appearance: "text" or "html" (default: "text").
    - name: defaults to today's date as "Jan 01, 2000" if omitted.
    - mailbox_ids: assigning mailboxes automatically activates warmup for the template.

    After creation, use get_user_template(id) to retrieve the full template with
    all system-generated fields (id, moderation_state, timestamps, etc.).
    Use get_user_templates_stats() to monitor performance once the template is warming.

    Parameters:
        subject: Email subject line (max 100 chars).
        body: Email body. Must contain {{ Recipient_Name }} for text templates.
        language_code: ISO 639-1 language code (e.g. "en", "fr").
        appearance: Template format — "text" or "html". Default "text".
        name: Human-readable label. Defaults to today's date if not provided.
        mailbox_ids: Optional list of mailbox IDs to assign. Activates warmup automatically.

    Returns:
        message: Confirmation string.
        id: ID of the newly created template.
    """
    template: dict = {"subject": subject, "body": body, "language_code": language_code, "appearance": appearance}
    if name:
        template["name"] = name
    if mailbox_ids:
        template["mailbox_ids"] = mailbox_ids
    return await _request("POST", "/api/v2/user_templates", json={"user_template": template})


# ---------------------------------------------------------------------------
# Tool 3: List templates (lightweight)
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_user_templates(
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    filter_name: Optional[str] = None,
    filter_searchable: Optional[str] = None,
    filter_subject: Optional[str] = None,
    filter_appearance: Optional[str] = None,
    filter_moderation_state: Optional[str] = None,
) -> dict:
    """
    List user templates returning only ID, name, and subject.

    Lighter than get_user_templates() — use this to browse or search templates
    when you don't need the full body content. Ideal for picking a template ID
    before calling get_user_template(id), update_user_template(id), or
    delete_user_template(id).

    Parameters:
        page: Page number (default: 1).
        per_page: Results per page (default: 20).
        filter_name: Filter by template name.
        filter_searchable: Search across name and subject.
        filter_subject: Filter by subject line.
        filter_appearance: One of "html", "text", "hubspot".
        filter_moderation_state: One of "approved", "rejected", "pending", "no_state".

    Returns:
        items: List of lightweight objects — each has id, name, subject only.
        pagination: current_page, total_pages, total_count, next_page, prev_page.
    """
    return await _request("GET", "/api/v2/user_templates/list", params={
        "page": page,
        "per_page": per_page,
        "filter[name]": filter_name,
        "filter[searchable]": filter_searchable,
        "filter[subject]": filter_subject,
        "filter[appearance]": filter_appearance,
        "filter[moderation_state]": filter_moderation_state,
    })


# ---------------------------------------------------------------------------
# Tool 4: Get single template
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_user_template(template_id: str) -> dict:
    """
    Retrieve complete details for a single template by its ID.

    Returns all fields for one template. Use list_user_templates() first to
    find the ID if you don't have it yet.

    Field value reference:
    - moderation_state: "approved", "rejected", or "pending"
    - provider: "warmy" or "hubspot"
    - appearance: "html" or "text"
    - warming: true if the template has mailboxes assigned and warmup is active

    Parameters:
        template_id: Numeric template ID (as a string).

    Returns:
        id, name, subject, body, appearance, warming, provider, moderation_state,
        language (name + code), created_at, updated_at.
    """
    return await _request("GET", f"/api/v2/user_templates/{template_id}")


# ---------------------------------------------------------------------------
# Tool 5: Update template
# ---------------------------------------------------------------------------

@mcp.tool()
async def update_user_template(
    template_id: str,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    name: Optional[str] = None,
    language_code: Optional[str] = None,
    appearance: Optional[str] = None,
    warming: Optional[bool] = None,
    run_moderation: Optional[bool] = None,
) -> dict:
    """
    Update an existing template. Only include the fields you want to change —
    omitted fields keep their current values.

    Rules:
    - subject: max 100 characters.
    - body: must still contain {{ Recipient_Name }} if appearance is "text".
    - language_code: ISO 639-1 format (e.g. "en", "es").
    - warming: can only be set to true if the template has mailboxes assigned.
    - run_moderation: when True, AI moderation runs synchronously during this
      request instead of in the background. Useful when you need the moderation
      result immediately.

    Use get_user_template(template_id) before updating to see the current values.
    Use get_user_templates_stats() after updating to confirm performance impact.

    Parameters:
        template_id: ID of the template to update.
        subject: New subject line (max 100 chars).
        body: New email body. Must contain {{ Recipient_Name }} for text templates.
        name: New display name.
        language_code: New ISO 639-1 language code.
        appearance: "text" or "html".
        warming: Enable/disable warmup (only true if mailboxes are assigned).
        run_moderation: Run AI moderation synchronously if True.

    Returns:
        Updated template object with all current field values.
    """
    template: dict = {}
    if subject is not None:
        template["subject"] = subject
    if body is not None:
        template["body"] = body
    if name is not None:
        template["name"] = name
    if language_code is not None:
        template["language_code"] = language_code
    if appearance is not None:
        template["appearance"] = appearance
    if warming is not None:
        template["warming"] = warming

    payload: dict = {"user_template": template}
    if run_moderation is not None:
        payload["run_moderation"] = run_moderation

    return await _request("PUT", f"/api/v2/user_templates/{template_id}", json=payload)


# ---------------------------------------------------------------------------
# Tool 10: List mailboxes
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_mailboxes(
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    response_type: Optional[str] = None,
    filter_email: Optional[str] = None,
    filter_group_id: Optional[str] = None,
    filter_providers: Optional[list[str]] = None,
    filter_domains: Optional[list[int]] = None,
    sorting_email: Optional[str] = None,
) -> dict:
    """
    Retrieve a paginated list of all mailboxes in the workspace.

    Two response modes:
    - Default: full mailbox data with all fields, sorted by created_at descending.
    - Simple (response_type="simple"): returns only id and email — faster, ideal for
      dropdowns or when you just need a mailbox_id for other tools like
      list_deliverability_checkers() or create_deliverability_checker().

    Note: sorting_email only works when response_type="simple".

    Parameters:
        page: Page number (default: 1).
        per_page: Items per page, min 1 max 100 (default: 25).
        response_type: Pass "simple" for lightweight id+email only response.
        filter_email: Substring search on email address (case-insensitive).
        filter_group_id: Filter by group ID.
        filter_providers: Filter by provider(s), e.g. ["gmail", "outlook", "mailgun"].
        filter_domains: Filter by domain ID(s).
        sorting_email: Sort by email — "asc" or "desc". Requires response_type="simple".

    Returns:
        Default: items with full mailbox data + pagination.
        Simple: items with id and email only + pagination.
    """
    params: dict = {
        "page": page,
        "per_page": per_page,
        "response_type": response_type,
        "filter[email]": filter_email,
        "filter[group_id]": filter_group_id,
        "sorting[email]": sorting_email,
    }
    if filter_providers:
        params["filter[providers][]"] = filter_providers
    if filter_domains:
        params["filter[domains][]"] = filter_domains
    return await _request("GET", "/api/v2/mailboxes", params=params)



# ---------------------------------------------------------------------------
# Tool 12: Get single mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_mailbox(mailbox_id: str) -> dict:
    """
    Get full details for a specific mailbox by ID.

    Returns health and configuration data including warmup status, DNS records,
    deliverability score, sending limits, and the latest deliverability test result.

    state_key values and their meaning:
        trial, updated, expired — subscription/plan states.
        reconnect, credentials, less_secure — authentication issues needing action.
        imap, domain, folder, quota, server — configuration or infrastructure problems.
        unusual_activity, invalid_email, full_storage — account-level issues.
        unconfigured_domain, web, inform, critical, temporary — various warning states.
        not_active — mailbox is paused.

    Use list_mailboxes(response_type="simple") to find mailbox IDs.
    Use list_deliverability_checkers(mailbox_id) to see test history for this mailbox.

    Parameters:
        mailbox_id: Mailbox ID (required).

    Returns:
        from_name, status, state_key, state_description, warmup_active, deliverability,
        dns_score, isp_score, temperature, sent_today, received_today, sending_limit,
        spf/dkim/dmarc/r_dns/mx_record/a_record status, warmup_language, warmup_topic,
        latest_deliverability_test, settings.
    """
    return await _request("GET", f"/api/v2/mailboxes/{mailbox_id}")



# ---------------------------------------------------------------------------
# Tool 19: List deliverability checkers for a mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_deliverability_checkers(
    mailbox_id: str,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> dict:
    """
    List all deliverability checker runs for a specific mailbox.

    Returns a paginated list of past deliverability tests with their title,
    unique token, creation date, and summary stats. Use this to browse test
    history or find a uniq_token to pass to get_deliverability_checker().

    Parameters:
        mailbox_id: ID of the mailbox to retrieve checkers for (required).
        page: Page number (default: 1).
        per_page: Results per page, max 25.

    Returns:
        items: List of checker summaries — title, uniq_token, created_date, stats.
        pagination: current_page, total_pages, total_count, next_page, prev_page.
    """
    return await _request("GET", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers", params={
        "page": page,
        "per_page": per_page,
    })


# ---------------------------------------------------------------------------
# Tool 11: Run mailbox deliverability check (create + poll + fetch in one call)
# ---------------------------------------------------------------------------

PENDING_STATUSES = {"pending", "in_progress", "processing", "running", "created", "init"}


@mcp.tool()
async def run_deliverability_check(
    mailbox_id: str,
    user_template_id: int,
    providers: Optional[list[str]] = None,
    timeout_seconds: int = 120,
) -> dict:
    """
    Run a full deliverability test for a connected mailbox and return results automatically.

    Combines create + poll + fetch into a single call — no manual steps required.
    Creates the checker, waits for it to complete, then returns the full report.

    What it checks:
    - Inbox placement per provider (where the email actually landed)
    - SPF, DKIM, DMARC authentication results
    - IP reputation and blacklist status
    - From header analysis
    - Overall delivery statistics

    Available providers: GOOGLE, ZOHO, YAHOO, OUTLOOK, GSUITE, ZOHOPRO, OUTLOOKBUSINESS, OTHER.
    Pass an empty list or omit providers to test against all available providers.

    Use list_mailboxes(response_type="simple") to find mailbox_id.
    Use list_user_templates() to find user_template_id.

    Parameters:
        mailbox_id: ID of the connected mailbox to test from (required).
        user_template_id: ID of the template to use as the test email (required).
        providers: Specific providers to test. Omit or pass [] for all providers.
        timeout_seconds: Max time to wait for results in seconds (default: 120).

    Returns:
        title, uniq_token, status — test identification.
        grouped_emails — results per provider showing inbox/spam placement.
        report_data — ips, spf, dkim, from header analysis, overall stats.
        spf_data, dkim_data, dmarc_data, blacklist_data — raw authentication data.
    """
    created = await _request("POST", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers", json={
        "user_template_id": user_template_id,
        "providers": providers if providers is not None else [],
    })

    if "error" in created:
        return created

    uniq_token = created.get("uniq_token")
    if not uniq_token:
        return {"error": "No uniq_token in response", "detail": created}

    deadline = time.time() + timeout_seconds
    poll_interval = 5

    while time.time() < deadline:
        result = await _request("GET", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers/{uniq_token}")
        if "error" in result:
            return result
        status = (result.get("check_status") or result.get("status") or "").lower()
        if status and status not in PENDING_STATUSES:
            return result
        await asyncio.sleep(poll_interval)

    return {"error": "Timeout", "detail": f"Check did not complete within {timeout_seconds}s. uniq_token='{uniq_token}' — results may still arrive; check your Warmy dashboard."}


# ---------------------------------------------------------------------------
# Tool 13: Create standalone deliverability checker (no mailbox required)
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_standalone_deliverability_checker(
    providers: list[str],
) -> dict:
    """
    Create a standalone deliverability test — no connected mailbox required.

    Returns seed addresses and a tracking token. After calling this tool, you must
    manually send your test email to all addresses in the returned emails list, then
    call get_standalone_deliverability_checker(uniq_token) to retrieve results
    (typically takes 3-5 minutes after sending).

    Two tracking options — include at least one in every message you send:
    - REF tracking: add email_ref_address to the To field alongside the seed addresses.
    - Code tracking: embed email_code in the subject or body of your test email.

    Use the Warmy possible_providers endpoint or docs to get the full list of valid
    provider names.

    Parameters:
        providers: List of provider names to test against (required).

    Returns:
        uniq_token: Unique test identifier — pass to get_standalone_deliverability_checker().
        emails: Seed addresses to send your test email to.
        email_ref_address: Reference address to add to the To field for REF-based tracking.
        email_code: Tracking code to embed in subject or body for code-based tracking.
    """
    return await _request("POST", "/api/v2/standalone_deliverability_checkers", json={
        "providers": providers,
    })


# ---------------------------------------------------------------------------
# Tool 14: Get standalone deliverability checker results
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_standalone_deliverability_checker(uniq_token: str) -> dict:
    """
    Retrieve results for a standalone deliverability test.

    Call this after you have sent your test email to all seed addresses returned by
    create_standalone_deliverability_checker(). Results typically take 3-5 minutes
    to appear after sending.

    Parameters:
        uniq_token: Unique test token (SID) from create_standalone_deliverability_checker() (required).

    Returns:
        uniq_token, check_status, created_at, created_date — test identification.
        report_data — detailed delivery analysis.
        grouped_emails — results grouped by email provider.
    """
    return await _request("GET", f"/api/v2/standalone_deliverability_checkers/{uniq_token}")


# ---------------------------------------------------------------------------
# Tool 15: Toggle auto checker settings for a mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
async def toggle_auto_checker(
    mailbox_id: str,
    active: bool,
    user_template_id: Optional[int] = None,
    next_check_date: Optional[str] = None,
    providers: Optional[list[str]] = None,
) -> dict:
    """
    Enable or disable automatic deliverability checks for a mailbox, and configure settings.

    When active, Warmy automatically runs deliverability tests on a schedule.
    Use this to turn auto-checking on/off or update which template and providers are used.
    To update multiple mailboxes at once, use mass_update_auto_checker() instead.

    Parameters:
        mailbox_id: ID of the mailbox to configure (required).
        active: True to enable auto-checking, False to disable (required).
        user_template_id: Template to use for auto checks. Uses account default if omitted.
        next_check_date: Schedule the next check on a specific date (format: YYYY-MM-DD).
        providers: List of providers to test. Uses all providers if omitted.

    Returns:
        id, user_template_id, active, message, next_check_date, providers — updated settings.
    """
    auto_checker_attributes: dict = {"active": active}
    if user_template_id is not None:
        auto_checker_attributes["user_template_id"] = user_template_id
    if next_check_date is not None:
        auto_checker_attributes["next_check_date"] = next_check_date
    if providers is not None:
        auto_checker_attributes["providers"] = providers

    return await _request("PUT", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers/toggle_auto_checker", json={
        "mailbox": {"auto_checker_attributes": auto_checker_attributes}
    })


# ---------------------------------------------------------------------------
# Tool 16: Mass update auto checker for multiple mailboxes
# ---------------------------------------------------------------------------

@mcp.tool()
async def mass_update_auto_checker(
    active: bool,
    mailbox_ids: Optional[list[int]] = None,
    user_template_id: Optional[int] = None,
) -> dict:
    """
    Enable or disable automatic deliverability checks across multiple mailboxes at once.

    Applies the same settings to all specified mailboxes in a single request.
    Pass an empty list or omit mailbox_ids to apply changes to ALL mailboxes in the account.

    Template behaviour:
    - Pass user_template_id to set a specific template for all affected mailboxes.
    - Pass null / omit to use the account default template (or reset to default if previously set).
    - To keep each mailbox's existing template unchanged, do not include user_template_id at all.

    Use toggle_auto_checker() instead if you need per-mailbox control (e.g. different
    next_check_date or providers per mailbox).

    Parameters:
        active: True to enable auto-checking, False to disable (required).
        mailbox_ids: List of mailbox IDs to update. Omit or pass empty list for all mailboxes.
        user_template_id: Template ID to assign. Omit to keep existing or use account default.

    Returns:
        message: Confirmation of how many mailboxes were updated.
    """
    payload: dict = {"active": active, "mailbox_ids": mailbox_ids or []}
    if user_template_id is not None:
        payload["user_template_id"] = user_template_id

    return await _request("PUT", "/api/v2/deliverability_checkers/mass_update_auto_checker", json={
        "mailbox": payload
    })


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    app = mcp.streamable_http_app()
    app.add_middleware(_TokenMiddleware)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), proxy_headers=True, forwarded_allow_ips="*")
