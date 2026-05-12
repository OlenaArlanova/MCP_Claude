from mcp.server.fastmcp import FastMCP
import httpx
import os
import time
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

mcp = FastMCP("Warmy Templates")

BASE_URL = "https://api.warmy.io"
TIMEOUT = 30.0
HOLDER_UID = "a66a9a755fe16f24fcb99dc8b5f25a50"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('WARMY_API_TOKEN', '')}",
        "Holder-Uid": HOLDER_UID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
    token = os.environ.get("WARMY_API_TOKEN", "")
    if not token:
        return {"error": "Missing credentials", "detail": "WARMY_API_TOKEN is not set. Please provide your Warmy API token."}

    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.request(method, f"{BASE_URL}{path}", headers=_headers(), params=clean_params, json=json)
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
def get_user_templates(
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
    return _request("GET", "/api/v2/user_templates", params={
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
def create_user_template(
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
    return _request("POST", "/api/v2/user_templates", json={"user_template": template})


# ---------------------------------------------------------------------------
# Tool 3: List templates (lightweight)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_user_templates(
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
    return _request("GET", "/api/v2/user_templates/list", params={
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
def get_user_template(template_id: str) -> dict:
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
    return _request("GET", f"/api/v2/user_templates/{template_id}")


# ---------------------------------------------------------------------------
# Tool 5: Update template
# ---------------------------------------------------------------------------

@mcp.tool()
def update_user_template(
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

    return _request("PUT", f"/api/v2/user_templates/{template_id}", json=payload)


# ---------------------------------------------------------------------------
# Tool 6: Delete template
# ---------------------------------------------------------------------------

@mcp.tool()
def delete_user_template(template_id: str) -> dict:
    """
    Permanently delete a template by its ID.

    This action cannot be undone. Use list_user_templates() to confirm the correct
    template ID before deleting. Use get_user_templates_stats() beforehand if you
    want to record performance data before removing the template.

    Parameters:
        template_id: ID of the template to delete.

    Returns:
        Confirmation of deletion.
    """
    return _request("DELETE", f"/api/v2/user_templates/{template_id}")


# ---------------------------------------------------------------------------
# Tool 7: Templates with performance stats
# ---------------------------------------------------------------------------

@mcp.tool()
def get_user_templates_stats(
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    filter_name: Optional[str] = None,
    filter_searchable: Optional[str] = None,
    filter_subject: Optional[str] = None,
    filter_appearance: Optional[str] = None,
    filter_moderation_state: Optional[str] = None,
) -> dict:
    """
    Retrieve templates with their performance metrics (sent count, reply rate, deliverability).

    Extends the standard template list with statistics per template. Use this to compare
    performance across templates or identify which ones need improvement.

    For deeper time-series and per-provider breakdown, use get_user_templates_statistics()
    with specific template_ids from this response.

    Parameters:
        page: Page number (default: 1).
        per_page: Results per page (default: 20).
        filter_name: Filter by template name.
        filter_searchable: Search across name and subject.
        filter_subject: Filter by subject line.
        filter_appearance: One of "html", "text", "hubspot".
        filter_moderation_state: One of "approved", "rejected", "pending", "no_state".

    Returns:
        items: List of templates, each with:
            id, name, subject — template identifiers.
            sent — sent count metrics.
            replies — reply rate metrics.
            deliverability — deliverability metrics.
        pagination: Pagination metadata.
    """
    return _request("GET", "/api/v2/user_templates/stats", params={
        "page": page,
        "per_page": per_page,
        "filter[name]": filter_name,
        "filter[searchable]": filter_searchable,
        "filter[subject]": filter_subject,
        "filter[appearance]": filter_appearance,
        "filter[moderation_state]": filter_moderation_state,
    })


# ---------------------------------------------------------------------------
# Tool 8: Aggregated statistics with time series
# ---------------------------------------------------------------------------

@mcp.tool()
def get_user_templates_statistics(
    types: Optional[list[str]] = None,
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    template_ids: Optional[list[int]] = None,
    providers: Optional[list[str]] = None,
) -> dict:
    """
    Retrieve aggregated template statistics with time series and per-provider breakdowns.

    More detailed than get_user_templates_stats() — returns trend data over time and
    per-provider metrics, not just per-template totals. Use this for analytics dashboards
    or diagnosing which email provider is causing deliverability issues.

    Parameters:
        types: Which data to return — "total" for aggregated, "by_providers" for per-provider
            breakdown. Pass both to get everything (default behavior when omitted).
        period: Predefined range — "today", "yesterday", "week", or "month".
            Use either period OR start_date/end_date, not both.
        start_date: Custom range start in ISO8601 format (YYYY-MM-DD).
        end_date: Custom range end in ISO8601 format (YYYY-MM-DD).
        template_ids: Limit results to specific template IDs. Use list_user_templates()
            or get_user_templates_stats() to find relevant IDs first.
        providers: Filter by email provider codes, e.g. ["gmail", "outlook", "yahoo", "zoho"].

    Returns:
        total.summary: Aggregated totals for sent, inbox, saved_from_spam, promotion.
        total.items: Time series — array of data points with date and metrics.
        by_providers.{provider}.summary: Same totals broken out per provider.
        by_providers.{provider}.items: Per-provider time series.
    """
    params: dict = {}
    if types:
        params["types[]"] = types
    if period:
        params["filter[period]"] = period
    if start_date:
        params["filter[start_date]"] = start_date
    if end_date:
        params["filter[end_date]"] = end_date
    if template_ids:
        params["filter[template_ids][]"] = template_ids
    if providers:
        params["filter[providers][]"] = providers

    return _request("GET", "/api/v2/user_templates/statistics", params=params)


# ---------------------------------------------------------------------------
# Tool 9: Domain providers
# ---------------------------------------------------------------------------

@mcp.tool()
def get_domain_providers(
    domain: str,
    date: Optional[str] = None,
) -> dict:
    """
    Retrieve inbox/spam delivery reports for a domain broken down by email provider.

    Shows how emails from a given domain perform across different providers
    (Gmail, Outlook, Yahoo, etc.) — how many land in inbox vs spam, and the spam ratio.
    Use this to identify which specific provider is causing deliverability problems.

    Two sets of metrics are returned per provider:
    - w_* (Warmy metrics): inbox/spam counts and ratio as measured by Warmy's network.
    - pc_* (provider metrics): inbox/spam/promotions counts and ratio as reported
      by the receiving provider.

    Combine with get_user_templates_statistics(providers=[...]) to correlate
    provider-level delivery issues with specific templates.

    Parameters:
        domain: Domain to check, e.g. "warmy.io" (required).
        date: Filter results to a specific date. Format: YYYY-MM-DD or YYYY.MM.DD.
            Omit to get the latest available data.

    Returns:
        items: List of per-provider reports, each containing:
            date, domain, provider — identifies the record.
            w_inbox, w_spam, w_spam_ratio — Warmy-measured delivery metrics.
            pc_inbox, pc_spam, pc_promotions, pc_spam_ratio — provider-reported metrics.
    """
    return _request("GET", "/api/v2/domain_providers", params={
        "filter[domain]": domain,
        "filter[date]": date,
    })


# ---------------------------------------------------------------------------
# Tool 10: List mailboxes
# ---------------------------------------------------------------------------

@mcp.tool()
def list_mailboxes(
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
    return _request("GET", "/api/v2/mailboxes", params=params)


# ---------------------------------------------------------------------------
# Tool 11: Create mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
def create_mailbox(
    email: str,
    provider: str,
    tariff_plan_type_id: int,
    from_name: Optional[str] = None,
    password: Optional[str] = None,
    smtp_address: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_ssl: Optional[bool] = None,
    smtp_user_name: Optional[str] = None,
    smtp_password: Optional[str] = None,
    additional_key: Optional[str] = None,
    use_imap: Optional[bool] = None,
    imap_address: Optional[str] = None,
    imap_port: Optional[int] = None,
    imap_ssl: Optional[bool] = None,
    imap_user_name: Optional[str] = None,
    imap_password: Optional[str] = None,
) -> dict:
    """
    Create a new mailbox for a supported email provider.

    Supported providers: gmail, outlook, yahoo, zoho, zohopro, aol, smtp, sendgrid, mailgun.
    For Google OAuth or Outlook OAuth reconnection, use this same endpoint.

    Required fields by provider type:
    - Gmail / Yahoo / Outlook / Zoho / Zohopro / Aol: email, password, provider, tariff_plan_type_id.
    - SMTP: email, smtp_port, smtp_address, smtp_ssl, smtp_user_name, smtp_password, tariff_plan_type_id.
    - SendGrid / Mailgun: same as SMTP plus additional_key.

    After creation, use get_mailbox(id) to check status and state_key.
    Use list_mailboxes(response_type="simple") to find IDs of existing mailboxes.

    Parameters:
        email: Mailbox email address (required).
        provider: Provider name — gmail, outlook, yahoo, zoho, smtp, sendgrid, mailgun, etc. (required).
        tariff_plan_type_id: Tariff plan ID to assign (required).
        from_name: Sender display name.
        password: Account password (for standard providers).
        smtp_address / smtp_port / smtp_ssl / smtp_user_name / smtp_password: SMTP config.
        additional_key: Extra auth key for SendGrid/Mailgun.
        use_imap / imap_address / imap_port / imap_ssl / imap_user_name / imap_password: IMAP config.

    Returns:
        message: Confirmation.
        data.id: New mailbox ID.
        data.tariff_plan_type_id: Assigned plan.
    """
    mailbox: dict = {"email": email, "provider": provider, "tariff_plan_type_id": tariff_plan_type_id}
    for key, val in [
        ("from_name", from_name), ("password", password),
        ("smtp_address", smtp_address), ("smtp_port", smtp_port), ("smtp_ssl", smtp_ssl),
        ("smtp_user_name", smtp_user_name), ("smtp_password", smtp_password),
        ("additional_key", additional_key), ("use_imap", use_imap),
        ("imap_address", imap_address), ("imap_port", imap_port), ("imap_ssl", imap_ssl),
        ("imap_user_name", imap_user_name), ("imap_password", imap_password),
    ]:
        if val is not None:
            mailbox[key] = val
    return _request("POST", "/api/v2/mailboxes", json={"mailbox": mailbox})


# ---------------------------------------------------------------------------
# Tool 12: Get single mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
def get_mailbox(mailbox_id: str) -> dict:
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
    return _request("GET", f"/api/v2/mailboxes/{mailbox_id}")


# ---------------------------------------------------------------------------
# Tool 13: Update mailbox settings
# ---------------------------------------------------------------------------

@mcp.tool()
def update_mailbox(
    mailbox_id: str,
    user_max_limit: Optional[int] = None,
    reply_rate: Optional[int] = None,
    speed_mode: Optional[str] = None,
    setting_mode: Optional[str] = None,
    start_on_day_one: Optional[int] = None,
    increase_per_day: Optional[int] = None,
    settings_id: Optional[int] = None,
) -> dict:
    """
    Update warmup settings for a mailbox.

    Two configuration forms exist depending on the workspace type:
    - Speed form (most workspaces): use speed_mode, user_max_limit, reply_rate.
    - Detail form (custom, contact Warmy support to enable): use setting_mode,
      start_on_day_one, increase_per_day, user_max_limit, reply_rate.

    Only include the fields you want to change. reply_rate must not exceed 35.
    Use get_mailbox(mailbox_id) first to see current settings and settings_id.

    Parameters:
        mailbox_id: ID of the mailbox to update (required).
        settings_id: Settings record ID from get_mailbox(). Not required but recommended.
        speed_mode: "slow", "medium", or "fast" (speed form only).
        user_max_limit: Maximum daily email send limit.
        reply_rate: Reply rate percentage, max 35.
        setting_mode: "detail_default" or "detail_custom" (detail form only).
        start_on_day_one: Starting email count on day one (detail form only).
        increase_per_day: Daily ramp-up increment (detail form only).

    Returns:
        Confirmation message array.
    """
    mailbox: dict = {}
    if settings_id is not None:
        mailbox["id"] = settings_id
    for key, val in [
        ("speed_mode", speed_mode), ("user_max_limit", user_max_limit),
        ("reply_rate", reply_rate), ("setting_mode", setting_mode),
        ("start_on_day_one", start_on_day_one), ("increase_per_day", increase_per_day),
    ]:
        if val is not None:
            mailbox[key] = val
    return _request("PUT", f"/api/v2/mailboxes/{mailbox_id}", json={"mailbox": mailbox})


# ---------------------------------------------------------------------------
# Tool 14: Update mailbox state (activate / pause)
# ---------------------------------------------------------------------------

@mcp.tool()
def update_mailbox_state(mailbox_id: str, state: str) -> dict:
    """
    Activate or pause a mailbox.

    Use this to pause warmup temporarily (e.g. during a domain migration or
    account issue) or reactivate it. Check state_key from get_mailbox() first —
    some states like "credentials" or "reconnect" require fixing the underlying
    issue before activation will work.

    Parameters:
        mailbox_id: ID of the mailbox to update (required).
        state: "activate!" to start warmup, "pause!" to stop it (required).

    Returns:
        message: Confirmation of the state change.
    """
    return _request("PUT", f"/api/v2/mailboxes/{mailbox_id}/update_state", json={
        "mailbox": {"state": state}
    })


# ---------------------------------------------------------------------------
# Tool 15: Change mailbox tariff plan
# ---------------------------------------------------------------------------

@mcp.tool()
def change_mailbox_tariff_plan(mailbox_id: str, tariff_plan_type_id: Optional[int] = None) -> dict:
    """
    Update the tariff plan assigned to a mailbox.

    Pass a tariff_plan_type_id to assign a specific plan, or omit it (pass None)
    to set the plan to "unselected".

    Parameters:
        mailbox_id: ID of the mailbox to update (required).
        tariff_plan_type_id: Plan ID to assign, or None to unselect the current plan.

    Returns:
        message: Confirmation of the plan change.
    """
    return _request("PUT", f"/api/v2/mailboxes/{mailbox_id}/change_tariff_plan", json={
        "mailbox": {"tariff_plan_type_id": tariff_plan_type_id}
    })


# ---------------------------------------------------------------------------
# Tool 16: Reconnect mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
def reconnect_mailbox(
    mailbox_id: str,
    from_name: Optional[str] = None,
    password: Optional[str] = None,
    smtp_address: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_ssl: Optional[bool] = None,
    smtp_user_name: Optional[str] = None,
    smtp_password: Optional[str] = None,
    additional_key: Optional[str] = None,
    use_imap: Optional[bool] = None,
    imap_address: Optional[str] = None,
    imap_port: Optional[int] = None,
    imap_ssl: Optional[bool] = None,
    imap_user_name: Optional[str] = None,
    imap_password: Optional[str] = None,
    tariff_plan_type_id: Optional[int] = None,
) -> dict:
    """
    Reconnect a mailbox with updated credentials or configuration (SMTP/IMAP providers only).

    Use this when get_mailbox() shows state_key of "reconnect" or "credentials" —
    it means the current credentials have expired or changed and need updating.

    Note: For Google OAuth and Outlook OAuth mailboxes, use create_mailbox() instead
    to reconnect — this endpoint only supports SMTP/IMAP-based providers.

    Parameters:
        mailbox_id: ID of the mailbox to reconnect (required).
        from_name: Updated sender display name.
        password: Updated account password.
        smtp_address / smtp_port / smtp_ssl / smtp_user_name / smtp_password: Updated SMTP config.
        additional_key: Updated API key for SendGrid/Mailgun.
        use_imap / imap_address / imap_port / imap_ssl / imap_user_name / imap_password: Updated IMAP config.
        tariff_plan_type_id: Tariff plan to assign on reconnect.

    Returns:
        message: Confirmation of reconnection.
    """
    mailbox: dict = {}
    for key, val in [
        ("from_name", from_name), ("password", password),
        ("smtp_address", smtp_address), ("smtp_port", smtp_port), ("smtp_ssl", smtp_ssl),
        ("smtp_user_name", smtp_user_name), ("smtp_password", smtp_password),
        ("additional_key", additional_key), ("use_imap", use_imap),
        ("imap_address", imap_address), ("imap_port", imap_port), ("imap_ssl", imap_ssl),
        ("imap_user_name", imap_user_name), ("imap_password", imap_password),
        ("tariff_plan_type_id", tariff_plan_type_id),
    ]:
        if val is not None:
            mailbox[key] = val
    return _request("POST", f"/api/v2/mailboxes/{mailbox_id}/reconnect", json={"mailbox": mailbox})


# ---------------------------------------------------------------------------
# Tool 17: Get mailbox domains list
# ---------------------------------------------------------------------------

@mcp.tool()
def get_mailbox_domains() -> dict:
    """
    Retrieve all unique domains from workspace mailboxes.

    Returns a flat list of domain IDs and names. Use the domain IDs with
    list_mailboxes(filter_domains=[...]) to filter mailboxes by domain, or
    with get_domain_providers(domain) to check deliverability per provider.

    Returns:
        domains: List of objects with id and name for each domain.
    """
    return _request("GET", "/api/v2/mailboxes/domains_list")


# ---------------------------------------------------------------------------
# Tool 18: Get mailbox providers list
# ---------------------------------------------------------------------------

@mcp.tool()
def get_mailbox_providers() -> dict:
    """
    Retrieve all email providers used by mailboxes in the workspace.

    Returns provider IDs and names. Use provider IDs with
    list_mailboxes(filter_providers=[...]) to filter mailboxes by provider, or
    with get_user_templates_statistics(providers=[...]) to filter stats by provider.

    Returns:
        providers: List of objects with id and name for each provider.
    """
    return _request("GET", "/api/v2/mailboxes/providers_list")


# ---------------------------------------------------------------------------
# Tool 19: List deliverability checkers for a mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
def list_deliverability_checkers(
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
    return _request("GET", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers", params={
        "page": page,
        "per_page": per_page,
    })


# ---------------------------------------------------------------------------
# Tool 11: Create deliverability checker
# ---------------------------------------------------------------------------

VALID_PROVIDERS = ["GOOGLE", "ZOHO", "YAHOO", "OUTLOOK", "GSUITE", "ZOHOPRO", "OUTLOOKBUSINESS", "OTHER"]


@mcp.tool()
def create_deliverability_checker(
    mailbox_id: str,
    user_template_id: int,
    providers: Optional[list[str]] = None,
) -> dict:
    """
    Run a new deliverability test for a mailbox.

    Sends a test email through the specified mailbox using the given template,
    then checks where it lands across email providers. Pass specific providers
    to test only those, or omit (or pass empty list) to test all available providers.

    Available providers: GOOGLE, ZOHO, YAHOO, OUTLOOK, GSUITE, ZOHOPRO, OUTLOOKBUSINESS, OTHER.

    After creation, use get_deliverability_checker(mailbox_id, uniq_token) with the
    returned uniq_token to retrieve full results once the test completes.
    Use list_user_templates() to find the user_template_id if needed.

    Parameters:
        mailbox_id: ID of the mailbox to run the test from (required).
        user_template_id: ID of the template to use for the test email (required).
        providers: List of provider names to test against. Pass empty list or omit for all providers.

    Returns:
        uniq_token: Token to use with get_deliverability_checker() to fetch results.
    """
    return _request("POST", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers", json={
        "user_template_id": user_template_id,
        "providers": providers if providers is not None else [],
    })


# ---------------------------------------------------------------------------
# Tool 12: Run deliverability check and return full results automatically
# ---------------------------------------------------------------------------

PENDING_STATUSES = {"pending", "in_progress", "processing", "running", "created"}


@mcp.tool()
def run_deliverability_check(
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
    created = _request("POST", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers", json={
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
        result = _request("GET", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers/{uniq_token}")
        if "error" in result:
            return result
        status = (result.get("status") or "").lower()
        if status and status not in PENDING_STATUSES:
            return result
        time.sleep(poll_interval)

    return {"error": "Timeout", "detail": f"Check did not complete within {timeout_seconds}s. Use get_deliverability_checker(mailbox_id='{mailbox_id}', uniq_token='{uniq_token}') to fetch results later."}


# ---------------------------------------------------------------------------
# Tool 13: Get full deliverability checker results
# ---------------------------------------------------------------------------

@mcp.tool()
def get_deliverability_checker(mailbox_id: str, uniq_token: str) -> dict:
    """
    Retrieve full results for a specific deliverability checker run.

    Returns comprehensive test data including inbox placement per provider,
    authentication checks (SPF, DKIM, DMARC), blacklist status, IP reputation,
    and overall stats. Use list_deliverability_checkers() to find uniq_token values.

    Response fields:
        title, uniq_token, status — test identification and current status.
        grouped_emails — email results grouped by provider.
        report_data — detailed analysis:
            ips: IP reputation data.
            spf: SPF authentication result.
            dkim: DKIM signature results.
            from: From header analysis.
            stats: Overall delivery statistics.
        spf_data, dkim_data, dmarc_data — raw authentication record data.
        blacklist_data — blacklist check results.

    Parameters:
        mailbox_id: ID of the mailbox the test was run from (required).
        uniq_token: Unique token from create_deliverability_checker() or
            list_deliverability_checkers() (required).

    Returns:
        Full deliverability report including placement, authentication, and blacklist results.
    """
    return _request("GET", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers/{uniq_token}")


# ---------------------------------------------------------------------------
# Tool 13: Toggle auto checker settings for a mailbox
# ---------------------------------------------------------------------------

@mcp.tool()
def toggle_auto_checker(
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

    return _request("PUT", f"/api/v2/mailboxes/{mailbox_id}/deliverability_checkers/toggle_auto_checker", json={
        "mailbox": {"auto_checker_attributes": auto_checker_attributes}
    })


# ---------------------------------------------------------------------------
# Tool 14: Mass update auto checker for multiple mailboxes
# ---------------------------------------------------------------------------

@mcp.tool()
def mass_update_auto_checker(
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

    return _request("PUT", "/api/v2/deliverability_checkers/mass_update_auto_checker", json={
        "mailbox": payload
    })


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
