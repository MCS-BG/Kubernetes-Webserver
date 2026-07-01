# Strategic Roadmap: Business Vertical & Process Audit Framework

A standard taxonomy of business functions ("verticals") used to structure
every client audit, regardless of industry. Where `01-target-market-research.md`
segments the *market* by industry (wineries, law firms, venues...), this
document segments the *inside of any one business* by function, so an audit
of a wedding venue and an audit of a distillery use the same skeleton. It's
the shared reference for the audit playbook (Doc 03), the automation roadmap
(Doc 04), and the client-facing Company OS (Doc 02).

This list is intentionally a starting set — extend it with additional
verticals (e.g., R&D, e-commerce/fulfillment, facilities) whenever a client's
business model needs one that isn't listed.

## How to use this framework during an audit

For each vertical that applies to the client's business:
1. Confirm whether the vertical exists in this business at all (e.g., a law
   firm has no Manufacturing vertical; a distillery does).
2. Walk through the **typical processes** and **audit questions** for that
   vertical.
3. Score maturity 1-5 (1 = fully manual/ad hoc, 5 = fully automated with
   monitoring) using the same rubric as Doc 03.
4. Flag **common shortcomings** that match what you observe.
5. Note which automation phase/play in Doc 04 addresses each gap.

## Core verticals

### 1. Sales
**Scope:** everything from first inquiry to signed/closed business.
**Typical processes:** lead capture, qualification, quoting/proposals,
follow-up cadence, closing, upsell/renewal.
**Common shortcomings:** leads go unanswered for hours/days; no CRM of
record — leads live in email/text/memory; follow-up stops after 1-2 touches;
quotes are built manually per request; no visibility into pipeline value.
**Audit questions:** Where do leads land? Who responds and how fast? What
happens if the first responder is unavailable? How is a quote/proposal
produced? What triggers a follow-up, and how many times does it happen?
**Feeds into:** Doc 04 Phase 2 (CRM + lead scoring/sequencing), Phase 3
(AI proposal generation).

### 2. Marketing
**Scope:** how the business generates awareness and demand.
**Typical processes:** brand/positioning, content and campaigns, channel
management (social, email, referral/chamber), review/reputation generation,
seasonal promotion planning.
**Common shortcomings:** marketing is reactive/ad hoc with no calendar;
reviews aren't systematically requested; no tracking of which channel
actually produces booked business; seasonal peaks aren't planned for in
advance.
**Audit questions:** What drives most new business today — referral, search,
social, repeat? Is there a content/campaign calendar? Is review generation
systematic or occasional? Can you tell which channel a given lead came from?
**Feeds into:** Doc 04 Phase 1 (automated review requests), Phase 3
(predictive/seasonal marketing automation).

### 3. Operations / Service Delivery
**Scope:** the handoff from "sold" to "delivered" — scheduling, fulfillment,
execution, quality control, vendor/staff coordination.
**Typical processes:** booking/scheduling, day-of or project execution
checklists, staff/vendor coordination, quality control, handling exceptions
(cancellations, rescheduling, complaints).
**Common shortcomings:** scheduling is manual back-and-forth; no
standardized checklist for delivery, so quality depends on who's working;
no-show/cancellation handling is inconsistent; handoffs between sales and
delivery drop information.
**Audit questions:** How does a booked customer get onto the calendar? What
happens between booking and delivery day? Is there a checklist, or does it
depend on who's on shift? How are no-shows/cancellations/exceptions handled?
**Feeds into:** Doc 04 Phase 1 (reminders/no-show reduction), Phase 2
(self-serve scheduling), Phase 3 (end-to-end agentic scheduling).

### 4. Accounting & Finance
**Scope:** money in, money out, and visibility into cash position.
**Typical processes:** invoicing, accounts receivable/collections, accounts
payable, payroll, budgeting, cash-flow forecasting, tax/compliance prep.
**Common shortcomings:** invoices go out late or inconsistently; collections
follow-up is manual or nonexistent; the owner can't see cash position without
asking the bookkeeper; no budget-to-actual tracking.
**Audit questions:** How long after service/delivery is an invoice sent? Who
follows up on late payments, and how? How does the owner currently check
cash position? Is there a budget, and is it compared to actuals?
**Feeds into:** Doc 04 Phase 2 (automated invoicing/AR follow-up, reporting
dashboard).

### 5. Manufacturing / Production
**Scope:** applies to any client that makes a physical product (wineries,
breweries, distilleries, and any goods-producing business) — production
scheduling, raw materials/inventory, quality control, equipment maintenance,
batch/lot tracking, and production-specific regulatory compliance (e.g.,
TABC/TTB licensing and reporting for alcohol producers).
**Typical processes:** production/batch scheduling, raw-material and
finished-goods inventory management, quality checks, equipment maintenance
scheduling, batch/lot record-keeping, regulatory filings.
**Common shortcomings:** inventory is tracked on paper or spreadsheets and
drifts from POS/sales data; no preventive-maintenance schedule (reactive
only); batch/lot records aren't centralized, complicating compliance
reporting; production scheduling doesn't account for event/tasting-room
demand.
**Audit questions:** How is raw-material and finished-goods inventory
tracked, and does it reconcile with POS/sales? Is equipment maintenance
scheduled or reactive? How are batch/lot records kept, and could you produce
them quickly for a regulatory audit?
**Feeds into:** Doc 04 winery/brewery/distillery vertical plays (POS/inventory
sync); this vertical often surfaces the highest compliance risk, so treat
gaps here as high priority regardless of automation effort.

## Expandable verticals

Add these as needed — most small businesses will have at least the first two
even if informally:

- **Human Resources / People Ops** — hiring, onboarding, scheduling/labor
  management, performance, retention. Common gap: scheduling and onboarding
  paperwork are fully manual.
- **Customer Service / Support** — post-sale inquiries, complaints, warranty/
  service issues, and how they loop back into reviews/reputation (Marketing)
  and product/process fixes (Operations).
- **IT & Data / Systems** — the tool stack itself: what's connected to what,
  where data lives, backup/security posture, and whether reporting requires
  manual reconciliation across systems. Frequently the root cause of gaps
  found in every other vertical.
- **Compliance / Legal / Risk** — contracts, licensing, insurance,
  regulatory reporting beyond what's covered under Manufacturing (e.g.,
  liquor liability, employment law, ADA/accessibility for venues).
- **R&D / Product Development** — for businesses that iterate on offerings
  (new blends, new packages, new service lines) — how new offerings are
  scoped, tested, and rolled out.
- **E-commerce / Fulfillment** — for businesses selling product online
  (wine clubs, retail bottle shops) — order management, shipping/compliance
  (interstate alcohol shipping rules), and customer communication.

## Mapping to Doc 01 target verticals

| Target industry | Verticals typically present | Verticals to prioritize in audit |
|---|---|---|
| Wedding/event venues | Sales, Marketing, Operations, Accounting, Compliance | Sales (inquiry response), Operations (day-of execution) |
| Wineries/breweries/distilleries | Sales, Marketing, Operations, Accounting, **Manufacturing**, Compliance, E-commerce | Manufacturing (inventory/compliance), Sales (tasting/event bookings) |
| Law firms / professional services | Sales, Marketing, Operations, Accounting, Compliance, IT & Data | Operations (intake/document automation), Compliance |
| Real estate brokerages | Sales, Marketing, Operations, Accounting | Sales (lead routing/nurture) |
| Home services / contractors | Sales, Marketing, Operations, Accounting, HR | Operations (dispatch/scheduling), Accounting (invoicing) |
| Medical/dental/wellness | Sales (intake), Marketing, Operations, Accounting, Compliance, HR | Operations (scheduling/no-shows), Accounting (insurance billing) |

Use this table to walk into an audit already knowing which verticals are
likely to matter most, then confirm and adjust based on what the client
actually shows you.
