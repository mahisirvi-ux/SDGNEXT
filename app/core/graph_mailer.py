"""Microsoft Graph API email transport for SDGNext.

Replaces the legacy Gmail SMTP transport. All outbound email flows
through send_graph_email(). Authentication uses the OAuth2
client-credentials flow; the access token is cached in-memory and
refreshed on expiry.
"""

import os
import time
import base64
import requests


# In-memory token cache
_token_cache = {
    "access_token": None,
    "expires_at": 0  # epoch seconds
}


def _config():
    """Lazy-load Graph configuration from environment.

    Called inside functions, not at module import time. This avoids
    import-order issues with dotenv loading.
    """
    return {
        "tenant_id": os.environ.get("GRAPH_TENANT_ID", ""),
        "client_id": os.environ.get("GRAPH_CLIENT_ID", ""),
        "client_secret": os.environ.get("GRAPH_CLIENT_SECRET", ""),
        "sender_mailbox": os.environ.get(
            "GRAPH_SENDER_MAILBOX", "delivery@businessnext.com"
        ),
    }


def _get_access_token():
    """Return a valid Graph access token, refreshing if expired.

    Raises RuntimeError on auth failure.
    """
    now = time.time()

    # Reuse cached token if it has > 5 min of life left
    if (_token_cache["access_token"]
            and _token_cache["expires_at"] > now + 300):
        return _token_cache["access_token"]

    cfg = _config()
    tenant_id = cfg["tenant_id"]
    client_id = cfg["client_id"]
    client_secret = cfg["client_secret"]

    if not all([tenant_id, client_id, client_secret]):
        raise RuntimeError(
            "Graph credentials missing. Check .env for "
            "GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET."
        )

    token_url = (
        f"https://login.microsoftonline.com/"
        f"{tenant_id}/oauth2/v2.0/token"
    )

    resp = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Graph token request failed "
            f"({resp.status_code}): {resp.text[:300]}"
        )

    data = resp.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 3600)

    if not token:
        raise RuntimeError(
            f"Graph token response missing access_token: "
            f"{resp.text[:300]}"
        )

    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + expires_in
    return token


def build_threading_headers(message_id=None, in_reply_to=None,
                            references=None):
    """Translate RFC-5322 threading values into Graph
    internetMessageHeaders entries.

    Graph API's internetMessageHeaders ONLY accepts custom headers
    starting with 'x-' or 'X-'. Standard headers (Message-ID,
    In-Reply-To, References) are rejected with
    InvalidInternetMessageHeader error.

    We prefix them as X-SDGNext-Message-ID, X-SDGNext-In-Reply-To,
    X-SDGNext-References to preserve threading metadata for our own
    tracking. Outlook/Gmail native threading relies on subject-line
    matching (our D4-Approach-2 safety net).

    Returns a list of {"name", "value"} dicts, or [].
    """
    headers = []
    if message_id:
        headers.append(
            {"name": "X-SDGNext-Message-ID", "value": message_id}
        )
    if in_reply_to:
        headers.append(
            {"name": "X-SDGNext-In-Reply-To", "value": in_reply_to}
        )
    if references:
        headers.append(
            {"name": "X-SDGNext-References", "value": references}
        )
    return headers


def send_graph_email(to_recipients, subject, html_body,
                     cc_recipients=None, internet_headers=None,
                     attachments=None, save_to_sent=True):
    """Send an email via Microsoft Graph.

    Args:
        to_recipients: list of email address strings
        subject: subject line string
        html_body: HTML content string
        cc_recipients: optional list of CC address strings
        internet_headers: optional list of dicts:
            [{"name": "In-Reply-To", "value": "<msg-id>"}]
        attachments: optional list of dicts for Graph fileAttachments:
            [{"name": "file.docx", "contentType": "...",
              "contentBytes": "<base64-string>"}]
        save_to_sent: whether Graph saves a copy to the sender's
            Sent Items (default True)

    Returns:
        {"success": bool, "error": str or None}

    Never raises — returns success=False on any failure so callers
    can log and continue (matches the old SMTP behavior of
    try/except around sendmail).
    """
    try:
        token = _get_access_token()
    except Exception as e:
        return {"success": False, "error": f"Auth failed: {e}"}

    cfg = _config()
    sender_mailbox = cfg["sender_mailbox"]

    sendmail_url = (
        f"https://graph.microsoft.com/v1.0/users/"
        f"{sender_mailbox}/sendMail"
    )

    # Build recipient blocks
    def _addr_list(addrs):
        return [
            {"emailAddress": {"address": a}}
            for a in (addrs or [])
            if a and a.strip()
        ]

    to_block = _addr_list(to_recipients)
    cc_block = _addr_list(cc_recipients)

    if not to_block and not cc_block:
        return {"success": False, "error": "No recipients provided"}

    message = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": html_body
        },
        "toRecipients": to_block,
    }

    if cc_block:
        message["ccRecipients"] = cc_block

    if internet_headers:
        # Graph API ONLY allows headers starting with 'x-' or 'X-'.
        # Filter out any standard headers to prevent 400 errors.
        safe_headers = [
            h for h in internet_headers
            if h.get("name", "").lower().startswith("x-")
        ]
        if safe_headers:
            message["internetMessageHeaders"] = safe_headers

    if attachments:
        message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": att["name"],
                "contentType": att["contentType"],
                "contentBytes": att["contentBytes"],
            }
            for att in attachments
        ]

    payload = {
        "message": message,
        "saveToSentItems": bool(save_to_sent)
    }

    try:
        resp = requests.post(
            sendmail_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=45
        )
    except Exception as e:
        return {"success": False, "error": f"Graph request error: {e}"}

    # Graph sendMail returns 202 Accepted on success
    if resp.status_code == 202:
        return {"success": True, "error": None}

    return {
        "success": False,
        "error": (
            f"Graph sendMail failed "
            f"({resp.status_code}): {resp.text[:300]}"
        )
    }


def find_sent_message(subject_filter, max_age_days=30):
    """Search the sender's Sent Items for a message matching subject.

    Uses Graph API: GET /users/{mailbox}/mailFolders/SentItems/messages
    with $filter on subject. Returns the Graph message ID (str) of the
    most recent match, or None if not found.

    This is used to find the original MoM email so follow-ups can be
    sent as replies (proper Outlook threading).
    """
    try:
        token = _get_access_token()
    except Exception:
        return None

    cfg = _config()
    sender_mailbox = cfg["sender_mailbox"]

    # Build OData filter — exact subject match
    # Escape single quotes in subject for OData
    # NOTE: Graph API does not support $orderby combined with $filter
    # on mailFolder messages. We fetch top results and pick the latest.
    safe_subject = subject_filter.replace("'", "''")
    url = (
        f"https://graph.microsoft.com/v1.0/users/{sender_mailbox}"
        f"/mailFolders/SentItems/messages"
        f"?$filter=subject eq '{safe_subject}'"
        f"&$top=10"
        f"&$select=id,subject,sentDateTime,conversationId"
    )

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
    except Exception:
        return None

    if resp.status_code != 200:
        print(f"[Graph] find_sent_message search failed ({resp.status_code}): {resp.text[:200]}")
        return None

    messages = resp.json().get("value", [])
    if not messages:
        return None

    # Pick the most recent message (can't use $orderby with $filter)
    if len(messages) > 1:
        messages.sort(
            key=lambda m: m.get("sentDateTime", ""),
            reverse=True
        )

    return messages[0].get("id")


def reply_to_sent_message(original_message_id, html_body,
                          to_recipients=None, cc_recipients=None, subject=None):
    """Send a reply to an existing message in the sender's mailbox.

    Uses Graph API: POST /users/{mailbox}/messages/{id}/reply
    This creates a proper threaded reply with:
    - Re: prefix on subject (automatic)
    - Correct In-Reply-To and References headers (automatic)
    - Conversation threading in Outlook AND Gmail

    Args:
        original_message_id: Graph message ID (from find_sent_message)
        html_body: HTML content for the reply body
        to_recipients: optional override of To recipients
        cc_recipients: optional override of CC recipients

    Returns:
        {"success": bool, "error": str or None}
    """
    try:
        token = _get_access_token()
    except Exception as e:
        return {"success": False, "error": f"Auth failed: {e}"}

    cfg = _config()
    sender_mailbox = cfg["sender_mailbox"]

    reply_url = (
        f"https://graph.microsoft.com/v1.0/users/{sender_mailbox}"
        f"/messages/{original_message_id}/reply"
    )

    # Build the reply payload
    payload = {
        "message": {
            "body": {
                "contentType": "HTML",
                "content": html_body
            }
        }
    }
    # Override Graph's default "RE: " prefix
    if subject:
        payload["message"]["subject"] = subject

    # Override recipients if provided
    def _addr_list(addrs):
        return [
            {"emailAddress": {"address": a}}
            for a in (addrs or [])
            if a and a.strip()
        ]

    if to_recipients:
        payload["message"]["toRecipients"] = _addr_list(to_recipients)
    if cc_recipients:
        payload["message"]["ccRecipients"] = _addr_list(cc_recipients)

    try:
        resp = requests.post(
            reply_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=45
        )
    except Exception as e:
        return {"success": False, "error": f"Graph request error: {e}"}

    # Reply endpoint returns 202 Accepted on success
    if resp.status_code == 202:
        return {"success": True, "error": None}

    return {
        "success": False,
        "error": (
            f"Graph reply failed "
            f"({resp.status_code}): {resp.text[:300]}"
        )
    }


def graph_permission_check():
    """Diagnostic: attempts a token fetch and a minimal Graph call to
    verify credentials and surface what permissions are available.

    Returns a dict describing findings. Safe to call from an admin
    endpoint.
    """
    cfg = _config()
    result = {
        "token_ok": False,
        "sender": cfg["sender_mailbox"],
        "tenant_configured": bool(cfg["tenant_id"]),
        "notes": []
    }

    try:
        token = _get_access_token()
        result["token_ok"] = True
        result["notes"].append("OAuth2 token acquired OK.")
    except Exception as e:
        result["notes"].append(f"Token fetch failed: {e}")
        return result

    # Decode the JWT payload (no verification — just to read the
    # 'roles' claim, which lists granted app permissions)
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            pad = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = base64.urlsafe_b64decode(pad)
            import json as _json
            claim_data = _json.loads(claims)
            roles = claim_data.get("roles", [])
            result["granted_permissions"] = roles
            result["notes"].append(
                f"App permissions (roles): {roles}"
            )

            # Flag what's needed
            if "Mail.Send" in roles:
                result["notes"].append("Mail.Send: present")
            else:
                result["notes"].append(
                    "Mail.Send: MISSING - email will fail"
                )

            if "OnlineMeetings.ReadWrite.All" in roles:
                result["notes"].append(
                    "OnlineMeetings.ReadWrite.All: present "
                    "(Teams meetings PR can proceed)"
                )
            else:
                result["notes"].append(
                    "OnlineMeetings.ReadWrite.All: missing - "
                    "Teams meeting PR will need this granted"
                )
    except Exception as e:
        result["notes"].append(
            f"Could not decode token claims: {e}"
        )

    return result
