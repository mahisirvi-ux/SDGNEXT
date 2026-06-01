"""
app/api/routes/kb.py
Knowledge Base CRUD with role-based access.

Roles:
  viewer  — read-only
  manager — create + edit (publishes as draft; admin must publish)
  admin   — full CRUD, publish/unpublish, pin, manage categories
"""

import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.domain import KBCategory, KBArticle, UserMaster

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


# ── Role helper ───────────────────────────────────────────────────────────────
def _require(user: UserMaster, *roles):
    if user.role not in roles:
        raise HTTPException(status_code=403, detail=f"Requires role: {' or '.join(roles)}")


# ── Slug helpers ──────────────────────────────────────────────────────────────
def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:270]


def _unique_slug(db: Session, base: str, exclude_id: int = None) -> str:
    slug, n = base, 1
    while True:
        q = db.query(KBArticle).filter(KBArticle.slug == slug)
        if exclude_id:
            q = q.filter(KBArticle.id != exclude_id)
        if not q.first():
            return slug
        slug = f"{base}-{n}"
        n += 1


# ── Serialiser ────────────────────────────────────────────────────────────────
def _out(a: KBArticle) -> dict:
    return {
        "id":             a.id,
        "category_id":    a.category_id,
        "category_name":  a.category.name  if a.category else "",
        "category_color": a.category.color if a.category else "indigo",
        "title":          a.title,
        "slug":           a.slug,
        "summary":        a.summary or "",
        "body":           a.body   or "",
        "tags":           a.tags   or [],
        "is_pinned":      a.is_pinned,
        "is_published":   a.is_published,
        "view_count":     a.view_count,
        "created_by":     a.created_by,
        "updated_by":     a.updated_by,
        "created_at":     a.created_at.isoformat() if a.created_at else None,
        "updated_at":     a.updated_at.isoformat() if a.updated_at else None,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────
class ArticleCreate(BaseModel):
    category_id: int
    title:       str
    summary:     Optional[str] = None
    body:        str = ""
    tags:        List[str] = []
    is_pinned:   bool = False


class ArticleUpdate(BaseModel):
    category_id: Optional[int]  = None
    title:       Optional[str]  = None
    summary:     Optional[str]  = None
    body:        Optional[str]  = None
    tags:        Optional[List[str]] = None
    is_pinned:   Optional[bool] = None


# ════════════════════════════════════════════════════════════
# CATEGORY ENDPOINTS
# ════════════════════════════════════════════════════════════

@router.get("/categories")
def list_categories(
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    cats = db.query(KBCategory).order_by(KBCategory.sort_order).all()
    result = []
    for c in cats:
        count = db.query(KBArticle).filter(
            KBArticle.category_id == c.id,
            KBArticle.is_published == True,
        ).count()
        result.append({
            "id":            c.id,
            "name":          c.name,
            "icon":          c.icon,
            "color":         c.color,
            "sort_order":    c.sort_order,
            "article_count": count,
        })
    return {"categories": result}


# ════════════════════════════════════════════════════════════
# ARTICLE ENDPOINTS
# ════════════════════════════════════════════════════════════

@router.get("/articles")
def list_articles(
    category_id:  Optional[int] = None,
    pinned_only:  bool          = False,
    limit:        int           = Query(20, le=100),
    offset:       int           = 0,
    db:           Session       = Depends(get_db),
    current_user: UserMaster    = Depends(get_current_user),
):
    q = db.query(KBArticle).filter(KBArticle.is_published == True)
    if category_id:
        q = q.filter(KBArticle.category_id == category_id)
    if pinned_only:
        q = q.filter(KBArticle.is_pinned == True)
    # Pinned first, then newest
    q = q.order_by(KBArticle.is_pinned.desc(), KBArticle.updated_at.desc())
    total    = q.count()
    articles = q.offset(offset).limit(limit).all()
    return {"total": total, "articles": [_out(a) for a in articles]}


@router.get("/search")
def search_articles(
    q:            str      = Query(..., min_length=1),
    db:           Session  = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    term    = f"%{q.lower()}%"
    results = db.query(KBArticle).filter(
        KBArticle.is_published == True,
        or_(
            KBArticle.title.ilike(term),
            KBArticle.summary.ilike(term),
            KBArticle.body.ilike(term),
        ),
    ).order_by(KBArticle.is_pinned.desc(), KBArticle.updated_at.desc()).limit(20).all()
    return {"results": [_out(a) for a in results]}


@router.get("/articles/{article_id}")
def get_article(
    article_id:   int,
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    a = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Article not found")
    a.view_count = (a.view_count or 0) + 1
    db.commit()
    return _out(a)


@router.post("/articles", status_code=201)
def create_article(
    payload:      ArticleCreate,
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    _require(current_user, "admin", "manager")
    if not db.query(KBCategory).filter(KBCategory.id == payload.category_id).first():
        raise HTTPException(status_code=400, detail="Category not found")

    slug         = _unique_slug(db, _slugify(payload.title))
    # Managers always save as draft; admins auto-publish
    is_published = (current_user.role == "admin")
    is_pinned    = payload.is_pinned if current_user.role == "admin" else False

    article = KBArticle(
        category_id  = payload.category_id,
        title        = payload.title.strip(),
        slug         = slug,
        summary      = payload.summary,
        body         = payload.body,
        tags         = payload.tags,
        is_pinned    = is_pinned,
        is_published = is_published,
        created_by   = current_user.full_name,
        updated_by   = current_user.full_name,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return {"message": "Article created", "article": _out(article)}


@router.put("/articles/{article_id}")
def update_article(
    article_id:   int,
    payload:      ArticleUpdate,
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    _require(current_user, "admin", "manager")
    a = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Article not found")

    if payload.title is not None:
        a.title = payload.title.strip()
        a.slug  = _unique_slug(db, _slugify(payload.title), exclude_id=article_id)
    if payload.category_id is not None:
        a.category_id = payload.category_id
    if payload.summary is not None:
        a.summary = payload.summary
    if payload.body is not None:
        a.body = payload.body
    if payload.tags is not None:
        a.tags = payload.tags
    if payload.is_pinned is not None and current_user.role == "admin":
        a.is_pinned = payload.is_pinned

    a.updated_by = current_user.full_name
    db.commit()
    return {"message": "Article updated", "article": _out(a)}


@router.put("/articles/{article_id}/publish")
def toggle_publish(
    article_id:   int,
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    _require(current_user, "admin")
    a = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Article not found")
    a.is_published = not a.is_published
    db.commit()
    return {"message": f"Article {'published' if a.is_published else 'unpublished'}", "is_published": a.is_published}


@router.delete("/articles/{article_id}", status_code=204)
def delete_article(
    article_id:   int,
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    _require(current_user, "admin")
    a = db.query(KBArticle).filter(KBArticle.id == article_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Article not found")
    db.delete(a)
    db.commit()


# ════════════════════════════════════════════════════════════
# SEED HELPER  (called by startup AND the manual endpoint)
# ════════════════════════════════════════════════════════════

def seed_kb_data(db: Session) -> dict:
    """Idempotent: creates default categories + starter articles.
    Safe to call multiple times — skips if categories already exist."""
    if db.query(KBCategory).count() > 0:
        return {"skipped": True, "message": "KB already seeded"}

    cats = [
        KBCategory(name="EDS Development",       icon="api",     color="indigo", sort_order=1),
        KBCategory(name="Service Provider (SP)",  icon="sop",     color="teal",   sort_order=2),
        KBCategory(name="XSLT & Transformations", icon="guide",   color="blue",   sort_order=3),
        KBCategory(name="Connection Setup",       icon="release", color="pink",   sort_order=4),
        KBCategory(name="Best Practices",         icon="faq",     color="amber",  sort_order=5),
    ]
    db.add_all(cats)
    db.flush()
    cm = {c.name: c.id for c in cats}

    articles = [
        # ── EDS Development ─────────────────────────────────────────────────
        {
            "category_id": cm["EDS Development"],
            "title":    "EDS — Complete Development Guide",
            "summary":  "Full reference for building an External Data Source in CRMNEXT: General Info, Request Template, Response Mapping, and XSLT.",
            "is_pinned": True,
            "tags":     ["eds", "crmnext", "datasource", "request-template", "xslt"],
            "body": """<h2>What is an EDS?</h2>
<p>An <strong>External Data Source (EDS)</strong> in CRMNEXT is a configured integration point that allows CRM entities (Leads, Accounts, Cases, etc.) to call an external system — typically a core banking system — and retrieve or post data in real time. Each EDS is associated with one <strong>Connection</strong> and exposes one <strong>Method</strong>.</p>

<h2>EDS Structure Overview</h2>
<p>An EDS record has three mandatory configuration areas:</p>
<ol>
  <li><strong>General Info</strong> — Name, Method Name, Connection, HTTP Method, Description</li>
  <li><strong>Request Template</strong> — The dynamic XML/JSON body sent to the bank API</li>
  <li><strong>Response Mapping</strong> — Output parameters extracted from the bank's response</li>
</ol>

<h2>Step 1 — General Info</h2>
<p>Navigate to <em>Admin → Integration → External Data Sources → New</em>.</p>
<ul>
  <li><strong>Name</strong>: Use the pattern <code>[Module]_[Action]_[System]</code>, e.g. <code>Lead_GetCIF_CBS</code></li>
  <li><strong>Method Name</strong>: Short camelCase identifier used in CRMNEXT rules, e.g. <code>getCIFDetails</code></li>
  <li><strong>Connection</strong>: Select the pre-configured RESTful Connection for this bank system</li>
  <li><strong>HTTP Method</strong>: Match the bank API spec — typically <code>POST</code> for data retrieval in banking APIs</li>
  <li><strong>Endpoint Path</strong>: Appended to the Connection base URL, e.g. <code>/api/v1/customer/details</code></li>
  <li><strong>Request Content Type</strong>: <code>application/json</code> for REST, <code>application/xml</code> for SOAP/XML</li>
</ul>

<h2>Step 2 — Request Template</h2>
<p>The Request Template is a <strong>dynamic body</strong> that merges CRM field values into the outgoing payload. CRMNEXT uses its own template syntax with double curly braces.</p>

<h3>JSON Request Template Example</h3>
<p>For a Lead screen calling a CBS account lookup:</p>
<pre><code>{
  "requestHeader": {
    "channelId": "CRMNXT",
    "requestId": "{{lead.id}}",
    "requestDateTime": "{{system.currentDateTime}}"
  },
  "requestBody": {
    "cifNumber": "{{lead.cif_number__c}}",
    "accountType": "{{lead.account_type__c}}"
  }
}</code></pre>

<h3>Key Template Variables</h3>
<ul>
  <li><code>{{entity.fieldApiName}}</code> — Pulls the value of a CRM field on the current record</li>
  <li><code>{{system.currentDateTime}}</code> — ISO-8601 timestamp at time of call</li>
  <li><code>{{system.loggedInUserId}}</code> — ID of the agent triggering the call</li>
  <li><code>{{input.paramName}}</code> — Value passed in from a Rule or button action at runtime</li>
</ul>

<h3>XML Request Template Example (SOAP-style)</h3>
<pre><code>&lt;Request&gt;
  &lt;Header&gt;
    &lt;Channel&gt;CRMNXT&lt;/Channel&gt;
    &lt;ReqId&gt;{{lead.id}}&lt;/ReqId&gt;
  &lt;/Header&gt;
  &lt;Body&gt;
    &lt;CIF&gt;{{lead.cif_number__c}}&lt;/CIF&gt;
  &lt;/Body&gt;
&lt;/Request&gt;</code></pre>

<h2>Step 3 — Response Mapping (Output Parameters)</h2>
<p>Output parameters define which fields to extract from the bank's JSON/XML response. Each parameter has:</p>
<ul>
  <li><strong>Parameter Name</strong>: The key you'll reference in Rules, e.g. <code>accountBalance</code></li>
  <li><strong>Response Path</strong>: JSONPath or XPath to the value, e.g. <code>responseBody.balance</code></li>
  <li><strong>Data Type</strong>: String, Number, Boolean, Date</li>
</ul>

<h3>JSONPath Examples</h3>
<ul>
  <li>Flat field: <code>responseBody.customerName</code></li>
  <li>Nested field: <code>responseBody.accountDetails.currentBalance</code></li>
  <li>Array item: <code>responseBody.accounts[0].accountNumber</code></li>
</ul>

<h2>Step 4 — Testing the EDS</h2>
<p>Use the <strong>Test</strong> button on the EDS form to send a live call with hardcoded sample values. Check the response preview to confirm output parameter extraction is correct before saving.</p>

<h2>Common Errors</h2>
<ul>
  <li><strong>"Connection not found"</strong> — The selected Connection may be inactive or mis-scoped</li>
  <li><strong>Empty output parameters</strong> — Verify the Response Path exactly matches the actual API response structure</li>
  <li><strong>Template variable not resolved</strong> — Confirm the CRM field API name is correct and the field exists on the entity</li>
  <li><strong>401 Unauthorized</strong> — The Connection's OAuth token has expired; check the token refresh settings</li>
</ul>""",
        },
        {
            "category_id": cm["EDS Development"],
            "title":    "EDS Naming Conventions and Versioning Standards",
            "summary":  "SDG standards for naming EDS, Method Names, Output Parameters, and managing version changes across environments.",
            "is_pinned": False,
            "tags":     ["eds", "naming", "conventions", "versioning", "standards"],
            "body": """<h2>Why Naming Conventions Matter</h2>
<p>CRMNEXT EDS names are referenced directly in Business Rules, Workflows, and Screen configurations. Inconsistent naming causes broken references when migrating between UAT and Production environments.</p>

<h2>EDS Name Pattern</h2>
<p>Use the format: <code>[Module]_[Verb]_[DataObject]_[System]</code></p>
<ul>
  <li><strong>Module</strong>: The CRM module using this EDS — <code>Lead</code>, <code>Account</code>, <code>Case</code>, <code>Contact</code></li>
  <li><strong>Verb</strong>: Action performed — <code>Get</code>, <code>Fetch</code>, <code>Create</code>, <code>Update</code>, <code>Validate</code></li>
  <li><strong>DataObject</strong>: What data — <code>CIF</code>, <code>AccountBalance</code>, <code>LoanDetails</code>, <code>KYC</code></li>
  <li><strong>System</strong>: Source system abbreviation — <code>CBS</code>, <code>DWH</code>, <code>LMS</code>, <code>FI</code></li>
</ul>
<p><strong>Examples:</strong></p>
<ul>
  <li><code>Lead_Get_CIF_CBS</code></li>
  <li><code>Account_Fetch_AccountBalance_CBS</code></li>
  <li><code>Case_Validate_KYC_DWH</code></li>
  <li><code>Contact_Create_ServiceRequest_LMS</code></li>
</ul>

<h2>Method Name Pattern</h2>
<p>Method names are camelCase and used in CRMNEXT Rule Engine calls:</p>
<ul>
  <li><code>getCIFDetails</code></li>
  <li><code>fetchAccountBalance</code></li>
  <li><code>validateKYCStatus</code></li>
</ul>
<p><strong>Do not</strong> use spaces, hyphens, or special characters in Method Names.</p>

<h2>Output Parameter Naming</h2>
<p>Output parameters should be camelCase and describe the exact data they carry:</p>
<ul>
  <li><code>customerName</code>, <code>accountBalance</code>, <code>loanStatus</code>, <code>branchCode</code></li>
  <li>Prefix with the system for disambiguation: <code>cbsAccountNumber</code>, <code>dwhSegmentCode</code></li>
  <li>Avoid generic names like <code>value1</code>, <code>data</code>, <code>result</code></li>
</ul>

<h2>Versioning</h2>
<p>When the bank changes an API contract (new fields, changed paths):</p>
<ol>
  <li>Create a new EDS with a version suffix: <code>Lead_Get_CIF_CBS_v2</code></li>
  <li>Update the Request Template and Output Parameters</li>
  <li>Test thoroughly in UAT before pointing any Rules to the new version</li>
  <li>Deprecate the old EDS — do not delete it until all Rules are migrated</li>
  <li>Document the change in the WUD and SDGNext touchpoint remarks</li>
</ol>

<h2>Environment-Specific Configuration</h2>
<p>EDS Connections must be separately configured in each environment (DEV, UAT, PROD). The EDS record itself migrates via package, but the <strong>Connection credentials</strong> (base URL, client ID, client secret) must be set manually per environment.</p>""",
        },

        # ── Service Provider (SP) ────────────────────────────────────────────
        {
            "category_id": cm["Service Provider (SP)"],
            "title":    "SP Development — Building a Service Provider in CRMNEXT",
            "summary":  "End-to-end guide for configuring a Service Provider: connection, method config, input/output parameters, and Rule Engine integration.",
            "is_pinned": True,
            "tags":     ["sp", "service-provider", "crmnext", "rule-engine", "outbound"],
            "body": """<h2>What is a Service Provider?</h2>
<p>A <strong>Service Provider (SP)</strong> in CRMNEXT is an outbound integration component that calls an external service and returns structured data to the CRM Rule Engine or Process flows. Unlike EDS (which is screen-driven), SP is typically invoked programmatically from <strong>Business Rules</strong>, <strong>Workflows</strong>, or <strong>Scheduled Jobs</strong>.</p>

<h2>SP vs EDS — When to Use Which</h2>
<ul>
  <li>Use <strong>EDS</strong> when data needs to be fetched or submitted from a <em>CRM screen</em> (Lead, Account, Case) triggered by a user action or page load</li>
  <li>Use <strong>SP</strong> when the integration is triggered by a <em>Rule, Workflow, or background process</em> — not directly by screen interaction</li>
  <li>Use <strong>SP</strong> for write-back operations: pushing CRM data to a bank system after a CRM record is created or updated</li>
</ul>

<h2>Step 1 — Create the SP Record</h2>
<p>Navigate to <em>Admin → Integration → Service Providers → New</em>.</p>
<ul>
  <li><strong>Name</strong>: Follow the pattern <code>[Trigger]_[Action]_[System]</code>, e.g. <code>LeadConvert_PushCIF_CBS</code></li>
  <li><strong>Type</strong>: Select <em>REST</em> or <em>SOAP</em> based on bank API</li>
  <li><strong>Connection</strong>: Select the RESTful or SOAP Connection</li>
  <li><strong>Endpoint</strong>: Relative path appended to the Connection base URL</li>
  <li><strong>HTTP Method</strong>: Typically <code>POST</code> for create/update, <code>GET</code> for retrieval</li>
</ul>

<h2>Step 2 — Input Parameters</h2>
<p>Input parameters define what data the Rule Engine passes into the SP at call time. Each input parameter maps to either a CRM field or a static/computed value.</p>
<ul>
  <li><strong>Parameter Name</strong>: Identifier used in the Request Template, e.g. <code>cifNumber</code></li>
  <li><strong>Mapped Field</strong>: The CRM entity field API name, e.g. <code>Lead.cif_number__c</code></li>
  <li><strong>Default Value</strong>: Optional fallback if the field is empty</li>
</ul>

<h2>Step 3 — Request Template</h2>
<p>The SP Request Template follows the same syntax as EDS. Use <code>{{input.paramName}}</code> to inject input parameter values:</p>
<pre><code>{
  "header": {
    "channel": "CRMNXT",
    "timestamp": "{{system.currentDateTime}}"
  },
  "payload": {
    "cifNumber": "{{input.cifNumber}}",
    "productCode": "{{input.productCode}}",
    "branchId": "{{input.branchId}}"
  }
}</code></pre>

<h2>Step 4 — Output Parameters</h2>
<p>Output parameters extract values from the SP response and make them available to downstream Rule Engine actions:</p>
<ul>
  <li><strong>Parameter Name</strong>: e.g. <code>cbsRefNumber</code></li>
  <li><strong>Response Path</strong>: JSONPath to value, e.g. <code>response.data.referenceNumber</code></li>
  <li>These values can be used in subsequent Rule conditions or Write-back actions</li>
</ul>

<h2>Step 5 — Calling the SP from a Rule</h2>
<p>In the CRMNEXT Rule Engine:</p>
<ol>
  <li>Add an <strong>Action</strong> of type <em>Call Service Provider</em></li>
  <li>Select your SP from the dropdown</li>
  <li>Map CRM fields to each Input Parameter</li>
  <li>Optionally map Output Parameters to CRM fields for write-back</li>
</ol>

<h2>Step 6 — Error Handling</h2>
<p>Configure fallback behaviour in the Rule when the SP returns a non-200 status or a business error code:</p>
<ul>
  <li>Define a <strong>Failure Output Parameter</strong> (e.g. <code>errorCode</code>, <code>errorMessage</code>) mapped from the error response body</li>
  <li>Add a Rule branch: <em>If errorCode is not empty → set CRM field to error message</em></li>
  <li>Use the <strong>Retry</strong> setting for transient network failures (max 3 retries recommended)</li>
</ul>

<h2>Checklist Before Go-Live</h2>
<ul>
  <li>SP tested successfully in UAT with real bank API credentials</li>
  <li>Error handling rule branch validated with a forced failure scenario</li>
  <li>Output parameters verified against actual response structure</li>
  <li>SP Name, Method, and parameters documented in the WUD</li>
  <li>Production Connection created and credentials stored securely</li>
</ul>""",
        },
        {
            "category_id": cm["Service Provider (SP)"],
            "title":    "SP — Handling Batch and Scheduled Invocations",
            "summary":  "How to trigger Service Providers from Scheduled Jobs and batch processes in CRMNEXT for bulk data sync scenarios.",
            "is_pinned": False,
            "tags":     ["sp", "batch", "scheduled-job", "bulk", "sync"],
            "body": """<h2>Overview</h2>
<p>Some bank integrations require periodic bulk data synchronisation — for example, fetching end-of-day account balances, refreshing KYC statuses overnight, or posting daily transaction summaries. CRMNEXT supports this via <strong>Scheduled Jobs</strong> that invoke a Service Provider against a list of CRM records.</p>

<h2>Architecture Pattern</h2>
<p>The typical batch SP pattern:</p>
<ol>
  <li>A <strong>Scheduled Job</strong> runs at a configured time (e.g. 2:00 AM daily)</li>
  <li>It queries a CRM report or list view to get the target records</li>
  <li>For each record, it calls the SP with that record's fields as input parameters</li>
  <li>The SP response is written back to the CRM record via output parameter mapping</li>
</ol>

<h2>Creating the Scheduled Job</h2>
<p>Navigate to <em>Admin → Automation → Scheduled Jobs → New</em>:</p>
<ul>
  <li><strong>Name</strong>: e.g. <code>NightlyKYCRefresh_DWH</code></li>
  <li><strong>Entity</strong>: The CRM entity to iterate over (e.g. Lead, Account)</li>
  <li><strong>Filter</strong>: Criteria for which records to process, e.g. <em>KYC Expiry Date is within 30 days</em></li>
  <li><strong>Schedule</strong>: Cron expression — <code>0 2 * * *</code> for 2 AM daily</li>
  <li><strong>Action</strong>: Call Service Provider → select your SP</li>
</ul>

<h2>Rate Limiting Considerations</h2>
<p>Bank APIs often enforce rate limits on bulk calls. Configure these safeguards:</p>
<ul>
  <li><strong>Batch Size</strong>: Process records in chunks of 50–100 rather than all at once</li>
  <li><strong>Delay Between Calls</strong>: Add a 200–500ms delay between SP invocations</li>
  <li><strong>Retry with Backoff</strong>: On HTTP 429 (Too Many Requests), wait 5s and retry</li>
  <li>Confirm rate limits with the bank's API team before scheduling</li>
</ul>

<h2>Monitoring and Alerts</h2>
<ul>
  <li>Enable <strong>Job Execution Logs</strong> in the Scheduled Job settings</li>
  <li>Set up a CRMNEXT alert if the job failure count exceeds a threshold</li>
  <li>Log the SP output parameter <code>errorCode</code> back to a custom field on the record for audit trail</li>
</ul>

<h2>Common Pitfalls</h2>
<ul>
  <li><strong>Token expiry mid-batch</strong>: Ensure the OAuth Connection is configured with auto token refresh; batch jobs often run longer than the token TTL</li>
  <li><strong>Partial failures</strong>: Design the job so each record is independent — a failure on record 47 should not stop records 48–100</li>
  <li><strong>Timezone mismatch</strong>: CRMNEXT server time may differ from the bank's expected timestamp format; always use UTC in request templates</li>
</ul>""",
        },

        # ── XSLT & Transformations ───────────────────────────────────────────
        {
            "category_id": cm["XSLT & Transformations"],
            "title":    "Writing XSLT for CRMNEXT EDS Response Mapping",
            "summary":  "Practical guide to writing XSLT stylesheets that transform bank XML/JSON responses into CRMNEXT output parameters.",
            "is_pinned": True,
            "tags":     ["xslt", "xml", "transformation", "eds", "response-mapping"],
            "body": """<h2>When is XSLT Used?</h2>
<p>CRMNEXT uses XSLT when the bank API returns <strong>XML</strong> (including SOAP responses) and you need to extract specific values into EDS or SP output parameters. For JSON responses, JSONPath is used instead — XSLT is only required for XML payloads.</p>

<h2>XSLT Basics for CRM Developers</h2>
<p>An XSLT stylesheet is an XML document that transforms one XML structure into another. CRMNEXT evaluates the XSLT against the raw bank response and extracts named output nodes.</p>

<h3>Skeleton XSLT for CRMNEXT</h3>
<pre><code>&lt;?xml version="1.0" encoding="UTF-8"?&gt;
&lt;xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"&gt;

  &lt;xsl:output method="xml" indent="yes"/&gt;

  &lt;xsl:template match="/"&gt;
    &lt;OutputParameters&gt;
      &lt;customerName&gt;
        &lt;xsl:value-of select="/Response/Body/CustomerDetails/Name"/&gt;
      &lt;/customerName&gt;
      &lt;accountBalance&gt;
        &lt;xsl:value-of select="/Response/Body/AccountInfo/Balance"/&gt;
      &lt;/accountBalance&gt;
      &lt;errorCode&gt;
        &lt;xsl:value-of select="/Response/Header/StatusCode"/&gt;
      &lt;/errorCode&gt;
    &lt;/OutputParameters&gt;
  &lt;/xsl:template&gt;

&lt;/xsl:stylesheet&gt;</code></pre>

<p>The element names inside <code>&lt;OutputParameters&gt;</code> must exactly match the <strong>Output Parameter Names</strong> defined in the EDS/SP configuration.</p>

<h2>Handling SOAP Namespaces</h2>
<p>SOAP responses include namespace declarations that must be registered in your XSLT:</p>
<pre><code>&lt;xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ns="http://bank.example.com/services"&gt;

  &lt;xsl:template match="/"&gt;
    &lt;OutputParameters&gt;
      &lt;cifNumber&gt;
        &lt;xsl:value-of select="//ns:GetCIFResponse/ns:CIFNumber"/&gt;
      &lt;/cifNumber&gt;
    &lt;/OutputParameters&gt;
  &lt;/xsl:template&gt;

&lt;/xsl:stylesheet&gt;</code></pre>

<h2>Conditional Extraction</h2>
<p>Use <code>xsl:choose</code> to handle optional fields or multiple response formats:</p>
<pre><code>&lt;accountStatus&gt;
  &lt;xsl:choose&gt;
    &lt;xsl:when test="/Response/Body/Account/Status"&gt;
      &lt;xsl:value-of select="/Response/Body/Account/Status"/&gt;
    &lt;/xsl:when&gt;
    &lt;xsl:otherwise&gt;UNKNOWN&lt;/xsl:otherwise&gt;
  &lt;/xsl:choose&gt;
&lt;/accountStatus&gt;</code></pre>

<h2>Extracting from Arrays</h2>
<p>To extract the first item from a repeated element:</p>
<pre><code>&lt;primaryAccount&gt;
  &lt;xsl:value-of select="/Response/Accounts/Account[1]/AccountNumber"/&gt;
&lt;/primaryAccount&gt;</code></pre>

<h2>String Operations</h2>
<ul>
  <li>Concatenate: <code>&lt;xsl:value-of select="concat(/Response/FirstName, ' ', /Response/LastName)"/&gt;</code></li>
  <li>Uppercase: <code>&lt;xsl:value-of select="translate(/Response/Status, 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')"/&gt;</code></li>
  <li>Substring: <code>&lt;xsl:value-of select="substring(/Response/AccountNumber, 1, 4)"/&gt;</code></li>
</ul>

<h2>Testing XSLT Locally</h2>
<p>Before uploading to CRMNEXT, test your XSLT against a sample response using free online tools like <strong>xsltransform.net</strong> or the <strong>Oxygen XML Editor</strong>. Paste the bank's sample response as the XML input and your stylesheet as the XSL input to verify output nodes are correctly extracted.</p>

<h2>Common Errors</h2>
<ul>
  <li><strong>Empty output parameter</strong> — XPath selector is incorrect; use an online XPath tester to verify the path against the actual response</li>
  <li><strong>Namespace error</strong> — SOAP namespace prefix is not declared in the stylesheet; add it to the <code>xsl:stylesheet</code> tag</li>
  <li><strong>Incorrect root node</strong> — The XPath starts from the wrong root; always use <code>//</code> for namespace-agnostic selection when unsure</li>
</ul>""",
        },

        # ── Connection Setup ─────────────────────────────────────────────────
        {
            "category_id": cm["Connection Setup"],
            "title":    "Configuring RESTful Connections in CRMNEXT",
            "summary":  "Step-by-step setup of RESTful API Connections including OAuth 2.0 client credentials, API key, and basic auth configurations.",
            "is_pinned": True,
            "tags":     ["connection", "oauth", "rest", "crmnext", "authentication"],
            "body": """<h2>Overview</h2>
<p>A <strong>Connection</strong> in CRMNEXT is a reusable credential and base URL configuration. Multiple EDS and SP records can share a single Connection if they call the same bank system. Connections are environment-specific — you must create separate connections for DEV, UAT, and Production.</p>

<h2>Creating a New Connection</h2>
<p>Navigate to <em>Admin → Integration → Connections → New RESTful Connection</em>.</p>

<h2>General Settings</h2>
<ul>
  <li><strong>Name</strong>: Use the pattern <code>[System]_[Environment]</code>, e.g. <code>CBS_UAT</code>, <code>DWH_PROD</code></li>
  <li><strong>Base URL</strong>: The root URL of the bank API — do not include the endpoint path here, e.g. <code>https://uat-api.bank.com/v2</code></li>
  <li><strong>Timeout</strong>: Set to 30 seconds as default; increase for heavy batch calls up to 60 seconds</li>
</ul>

<h2>Authentication Types</h2>

<h3>OAuth 2.0 — Client Credentials (Most Common)</h3>
<p>Used when the bank issues a Client ID and Client Secret for machine-to-machine calls:</p>
<ul>
  <li><strong>Auth Type</strong>: OAuth 2.0 Client Credentials</li>
  <li><strong>Token URL</strong>: e.g. <code>https://auth.bank.com/oauth2/token</code></li>
  <li><strong>Client ID</strong>: Provided by bank API team</li>
  <li><strong>Client Secret</strong>: Provided by bank API team (store securely; do not log)</li>
  <li><strong>Scope</strong>: As specified by bank, e.g. <code>crm.read crm.write</code></li>
  <li><strong>Token Refresh</strong>: Enable auto-refresh; set threshold to 60 seconds before expiry</li>
</ul>

<h3>API Key</h3>
<ul>
  <li><strong>Auth Type</strong>: API Key</li>
  <li><strong>Header Name</strong>: The header the bank expects, e.g. <code>X-API-Key</code> or <code>Ocp-Apim-Subscription-Key</code></li>
  <li><strong>Key Value</strong>: The API key string provided by the bank</li>
</ul>

<h3>Basic Authentication</h3>
<ul>
  <li><strong>Auth Type</strong>: Basic Auth</li>
  <li><strong>Username / Password</strong>: Base64-encoded at runtime by CRMNEXT; enter in plain text here</li>
</ul>

<h2>Request Headers</h2>
<p>Add headers that are common to all calls on this Connection — headers specific to individual endpoints go in the EDS/SP Request Template instead:</p>
<ul>
  <li><code>Content-Type: application/json</code></li>
  <li><code>Accept: application/json</code></li>
  <li><code>X-Channel-ID: CRMNXT</code></li>
</ul>

<h2>SSL / TLS Settings</h2>
<ul>
  <li>Enable <strong>Verify SSL Certificate</strong> in all non-DEV environments</li>
  <li>If the bank uses a self-signed cert in UAT, upload the certificate under <em>Trusted Certificates</em> rather than disabling verification entirely</li>
  <li>For mutual TLS (mTLS), upload the CRMNEXT client certificate and private key</li>
</ul>

<h2>IP Whitelisting</h2>
<p>Most bank APIs restrict inbound calls to whitelisted IP addresses. Provide the bank team with the <strong>CRMNEXT server outbound IP(s)</strong> before testing. Confirm whitelisting is active before the first UAT test call.</p>

<h2>Testing the Connection</h2>
<p>Use the <strong>Test Connection</strong> button after saving. A successful test confirms:</p>
<ul>
  <li>Base URL is reachable from CRMNEXT server</li>
  <li>OAuth token is obtained successfully (for OAuth connections)</li>
  <li>IP whitelisting is active</li>
</ul>""",
        },

        # ── Best Practices ───────────────────────────────────────────────────
        {
            "category_id": cm["Best Practices"],
            "title":    "SDG Integration Development — Standards and Best Practices",
            "summary":  "SDG-wide standards for EDS/SP development quality, documentation, testing, and handover to bank teams.",
            "is_pinned": True,
            "tags":     ["standards", "best-practices", "sdg", "quality", "handover"],
            "body": """<h2>Core Principles</h2>
<p>All SDG integration work on CRMNEXT bank projects follows these principles:</p>
<ol>
  <li><strong>Document first</strong> — No EDS or SP goes to UAT without a completed WUD (Work Unit Document)</li>
  <li><strong>Test with real data</strong> — Always validate against the bank's actual UAT API, not mock responses, before sign-off</li>
  <li><strong>Fail gracefully</strong> — Every integration must handle errors without crashing the CRM screen or workflow</li>
  <li><strong>Separate credentials per environment</strong> — DEV, UAT, and PROD must use separate Connections with separate credentials</li>
  <li><strong>Least privilege</strong> — Request only the OAuth scopes the integration actually needs</li>
</ol>

<h2>Development Workflow</h2>
<ol>
  <li><strong>Workshop</strong>: Conduct IDR (Integration Design Review) with bank to confirm API contract, auth method, request/response structure</li>
  <li><strong>WUD</strong>: Complete the Work Unit Document with all technical fields, sample payloads, and output mappings</li>
  <li><strong>EDS/SP Build</strong>: Create Connection → Create EDS or SP → Write Request Template → Map Output Parameters</li>
  <li><strong>Unit Test</strong>: Test via the EDS/SP Test button with real bank UAT credentials</li>
  <li><strong>Rule Integration</strong>: Wire EDS/SP into CRMNEXT Rules, Workflows, or Screens</li>
  <li><strong>SIT</strong>: System Integration Testing — end-to-end flow test with bank team present</li>
  <li><strong>Sign-off</strong>: Bank IDR sign-off recorded in SDGNext; status set to Completed</li>
</ol>

<h2>Error Handling Checklist</h2>
<p>Every EDS and SP must implement the following before UAT sign-off:</p>
<ul>
  <li>Output parameter <code>errorCode</code> mapped from the error response</li>
  <li>Output parameter <code>errorMessage</code> mapped from the error description field</li>
  <li>CRM Rule branch: <em>If errorCode is not empty → show error notification to agent</em></li>
  <li>For non-critical data (e.g. enrichment): silent failure — log the error but do not block the CRM screen</li>
  <li>For critical data (e.g. account creation): blocking failure — prevent save and show clear error to agent</li>
</ul>

<h2>Performance Guidelines</h2>
<ul>
  <li>EDS called on page load must respond within <strong>3 seconds</strong> — if the bank API is slower, discuss caching or async loading with the bank team</li>
  <li>Do not call the same EDS more than once per page load — cache the result in a CRM field if needed multiple times</li>
  <li>Batch SPs should be scheduled in the <strong>bank's off-peak window</strong> (typically midnight–4 AM)</li>
  <li>Always agree on <strong>SLA and rate limits</strong> with the bank API team before building; document in the WUD</li>
</ul>

<h2>Security Standards</h2>
<ul>
  <li>Never hardcode credentials in Request Templates — always use the Connection's auth configuration</li>
  <li>Do not log full request/response bodies in production — mask account numbers, CIF numbers, and PAN data in any debug logs</li>
  <li>Use HTTPS for all bank API calls — HTTP is not acceptable in any environment</li>
  <li>Rotate OAuth client secrets every 90 days or per bank policy, whichever is stricter</li>
</ul>

<h2>Handover Checklist to Bank Team</h2>
<ul>
  <li>WUD finalised and signed off by bank functional owner</li>
  <li>All EDS/SP names, Method Names, and Output Parameters documented</li>
  <li>Connection URLs for UAT and PROD documented separately</li>
  <li>CRMNEXT package export created and shared for migration</li>
  <li>Runbook provided: how to update credentials, how to re-test, who to contact if the integration breaks</li>
</ul>""",
        },
    ]

    for d in articles:
        slug = _unique_slug(db, _slugify(d["title"]))
        db.add(KBArticle(
            category_id  = d["category_id"],
            title        = d["title"],
            slug         = slug,
            summary      = d["summary"],
            body         = d["body"],
            tags         = d["tags"],
            is_pinned    = d["is_pinned"],
            is_published = True,
            created_by   = "System",
            updated_by   = "System",
        ))

    db.commit()
    return {"skipped": False, "categories": len(cats), "articles": len(articles)}


# ── Manual seed (admin only) ─────────────────────────────────────────────────
@router.post("/seed")
def manual_seed(
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    """Admin only — idempotent seed. Skips if KB already has categories."""
    _require(current_user, "admin")
    return seed_kb_data(db)


# ── Force reset + re-seed (admin only) ───────────────────────────────────────
@router.post("/seed/reset")
def reset_and_reseed(
    db:           Session    = Depends(get_db),
    current_user: UserMaster = Depends(get_current_user),
):
    """Admin only — WIPES all KB articles and categories, then re-seeds
    with the current default content. Use when the seed content has changed
    and you need to replace old placeholder articles."""
    _require(current_user, "admin")
    # Cascade delete: articles are deleted automatically via FK cascade
    deleted_articles = db.query(KBArticle).delete(synchronize_session=False)
    deleted_cats     = db.query(KBCategory).delete(synchronize_session=False)
    db.commit()
    result = seed_kb_data(db)
    result["deleted_articles"] = deleted_articles
    result["deleted_categories"] = deleted_cats
    return result
