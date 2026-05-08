"""
Generates report.pdf (Parts 1 + 2 of the PDC Assignment 2).

Output is constrained to <= 3 pages per the assignment rules.

Run:
    python report/generate_report.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
)

OUT_PATH = Path(__file__).with_name("report.pdf")


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
styles = getSampleStyleSheet()

H_TITLE = ParagraphStyle(
    "h_title",
    parent=styles["Heading1"],
    fontSize=14,
    leading=17,
    spaceAfter=2,
    textColor=colors.HexColor("#0b1d3a"),
)
H_META = ParagraphStyle(
    "h_meta",
    parent=styles["Normal"],
    fontSize=8.5,
    textColor=colors.HexColor("#3a3a3a"),
    spaceAfter=8,
)
H_PART = ParagraphStyle(
    "h_part",
    parent=styles["Heading2"],
    fontSize=11.5,
    leading=14,
    spaceBefore=6,
    spaceAfter=3,
    textColor=colors.HexColor("#0b1d3a"),
)
H_SUB = ParagraphStyle(
    "h_sub",
    parent=styles["Heading3"],
    fontSize=10,
    leading=12,
    spaceBefore=4,
    spaceAfter=1,
    textColor=colors.HexColor("#11366b"),
)
BODY = ParagraphStyle(
    "body",
    parent=styles["BodyText"],
    fontSize=9.3,
    leading=11.6,
    alignment=TA_JUSTIFY,
    spaceAfter=3,
)
BULLET = ParagraphStyle(
    "bullet",
    parent=BODY,
    leftIndent=11,
    bulletIndent=2,
    spaceAfter=1,
    alignment=TA_LEFT,
)
DIAG_CAPTION = ParagraphStyle(
    "diag_caption",
    parent=styles["Italic"],
    fontSize=8.5,
    leading=10,
    spaceBefore=2,
    spaceAfter=4,
    textColor=colors.HexColor("#444"),
)


def P(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text, style)


def B(text: str) -> Paragraph:
    return Paragraph(f"&bull;&nbsp; {text}", BULLET)


# --------------------------------------------------------------------------- #
# UML Sequence Diagram (Part 2 — Sync fix)
# --------------------------------------------------------------------------- #
class SequenceDiagram(Flowable):
    """
    UML sequence diagram showing two concurrent users editing the same
    document, the version-based optimistic-lock check on the server, the
    winner committing, and the loser receiving HTTP 409 Conflict.
    """

    WIDTH = 7.0 * inch
    HEIGHT = 4.05 * inch

    def wrap(self, _aw, _ah):
        return (self.WIDTH, self.HEIGHT)

    def draw(self):
        c = self.canv
        W, H = self.WIDTH, self.HEIGHT

        actors = [
            ("Alice (client)", 0.70 * inch),
            ("Bob (client)", 2.50 * inch),
            ("FastAPI", 4.55 * inch),
            ("Postgres", 6.40 * inch),
        ]

        top_y = H - 0.30 * inch
        bot_y = 0.35 * inch

        # Lifelines + actor headers
        c.setFont("Helvetica-Bold", 8.5)
        for label, x in actors:
            c.setFillColor(colors.HexColor("#e8eef9"))
            c.setStrokeColor(colors.HexColor("#11366b"))
            c.rect(x - 0.65 * inch, top_y, 1.30 * inch, 0.22 * inch,
                   stroke=1, fill=1)
            c.setFillColor(colors.HexColor("#0b1d3a"))
            c.drawCentredString(x, top_y + 0.07 * inch, label)
            c.setStrokeColor(colors.HexColor("#999"))
            c.setDash(2, 2)
            c.line(x, top_y, x, bot_y)
            c.setDash()

        ax = actors[0][1]
        bx = actors[1][1]
        sx = actors[2][1]
        dx = actors[3][1]

        def arrow(y, x1, x2, label, dashed=False, color="#0b1d3a"):
            c.setStrokeColor(colors.HexColor(color))
            c.setFillColor(colors.HexColor(color))
            if dashed:
                c.setDash(3, 2)
            c.setLineWidth(0.9)
            c.line(x1, y, x2, y)
            c.setDash()
            head = 5 if x2 > x1 else -5
            c.line(x2, y, x2 - head, y + 3)
            c.line(x2, y, x2 - head, y - 3)
            c.setFont("Helvetica", 7.8)
            mid = (x1 + x2) / 2
            c.drawCentredString(mid, y + 3, label)

        def note(y, x, w, h, txt, fill="#fff8d4"):
            c.setFillColor(colors.HexColor(fill))
            c.setStrokeColor(colors.HexColor("#b59a00"))
            c.rect(x, y, w, h, stroke=1, fill=1)
            c.setFillColor(colors.HexColor("#3a2d00"))
            c.setFont("Helvetica-Oblique", 7.5)
            c.drawString(x + 4, y + h - 9, txt)

        y = top_y - 0.20 * inch

        # 1. Both clients read version 42
        y -= 16
        arrow(y, ax, sx, "GET /docs/77")
        y -= 14
        arrow(y, sx, dx, "SELECT id, body, version")
        y -= 14
        arrow(y, dx, sx, "(body, version=42)", dashed=True)
        y -= 14
        arrow(y, sx, ax, "200 {body, version: 42}", dashed=True)

        y -= 18
        arrow(y, bx, sx, "GET /docs/77")
        y -= 14
        arrow(y, sx, bx, "200 {body, version: 42}", dashed=True)

        # 2. Both edit and submit
        y -= 18
        note(y - 6, ax - 0.55 * inch, 1.25 * inch, 14,
             "edits locally")
        note(y - 6, bx - 0.55 * inch, 1.25 * inch, 14,
             "edits locally")

        y -= 26
        arrow(y, ax, sx, "PUT /docs/77  if-match version=42 (Alice)")
        y -= 14
        arrow(y, sx, dx,
              "UPDATE ... SET version=43 WHERE id=77 AND version=42")
        y -= 14
        arrow(y, dx, sx, "rowcount = 1  (OK)", dashed=True, color="#0a7d2a")
        y -= 14
        arrow(y, sx, ax, "200 OK {version: 43}", dashed=True, color="#0a7d2a")

        # 3. Bob's stale write loses the CAS
        y -= 18
        arrow(y, bx, sx, "PUT /docs/77  if-match version=42 (Bob)",
              color="#a02020")
        y -= 14
        arrow(y, sx, dx,
              "UPDATE ... WHERE id=77 AND version=42",
              color="#a02020")
        y -= 14
        arrow(y, dx, sx, "rowcount = 0  (FAIL)", dashed=True, color="#a02020")
        y -= 14
        arrow(y, sx, bx,
              "409 Conflict {server_version: 43}",
              dashed=True, color="#a02020")

        y -= 18
        note(y - 6, bx - 0.55 * inch, 2.1 * inch, 14,
             "client refetches & merges, retries")


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
def build() -> None:
    doc = BaseDocTemplate(
        str(OUT_PATH),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="PDC Assignment 2 — Saleha Shoaib (BSCS23036)",
        author="Saleha Shoaib",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="main", showBoundary=0,
    )
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame])])

    story = []

    # ---------------- Header ---------------- #
    story += [
        P("PDC Assignment 2 &mdash; Building Resilient Distributed Systems",
          H_TITLE),
        P("<b>Saleha Shoaib</b> &nbsp;|&nbsp; BSCS23036 &nbsp;|&nbsp; "
          "Parallel and Distributed Computing &nbsp;|&nbsp; "
          "Repo: PDC-Sp24-BSCS23036-Shoaib", H_META),
    ]

    # ---------------- Part 1 ---------------- #
    story += [P("Part 1 &mdash; Analysis of the Naive Architecture", H_PART)]

    story += [P("1. Lost Update (Synchronization)", H_SUB)]
    story += [P(
        "Each edit is a read-modify-write (RMW) cycle: the client GETs document "
        "v=42, mutates a local copy, then PUTs the entire payload. The database "
        "row is updated atomically, but the <i>transaction boundary is per-write</i>, "
        "not across the user's edit session, so the two RMW cycles are not "
        "serializable. The DB has no precondition (no version column, no <i>SELECT "
        "FOR UPDATE</i>, no row-level lock taken at GET time), so the second write "
        "is a blind overwrite under last-writer-wins semantics. Concurrency control "
        "lives nowhere &mdash; not in the API, not in the data layer &mdash; which "
        "is the textbook lost-update / write-skew anomaly."
    )]

    story += [P("2. Dropped Cancellation Webhook (Coordination)", H_SUB)]
    story += [P(
        "Clerk delivers <i>subscription.deleted</i> with at-most-once semantics from "
        "our backend's perspective: it is a single fire-and-forget HTTP POST. If "
        "the TCP connection drops or our handler 5xx's, the event is gone, the "
        "user record never flips to <i>is_premium=False</i>, and our DB is now "
        "permanently divergent from Clerk's source of truth. There is no "
        "idempotency key, no durable inbox, no retry policy, and no reconciliation "
        "sweep, so even if Clerk did retry we would either double-process or have "
        "no way to deduplicate. This is a Two Generals problem in miniature: two "
        "independent services with no agreement protocol, exchanging exactly one "
        "lossy message."
    )]

    story += [P("3. Synchronous LLM Call (Fault Tolerance)", H_SUB)]
    story += [P(
        "The /chat handler issues a blocking outbound call with no per-request "
        "deadline (it inherits the upstream's 60 s socket timeout). Because the "
        "FastAPI worker is occupied for that entire window, the upstream's failure "
        "mode propagates into our process: under load the worker pool fills with "
        "stuck requests and queue depth on every <i>other</i> endpoint balloons. "
        "Health checks, login, even static assets stop responding. There is no "
        "bulkhead isolating the LLM client, no circuit to short-circuit the broken "
        "dependency, and no fallback &mdash; so one faulty dependency causes a "
        "cascading failure across the whole service."
    )]

    # ---------------- Part 2 ---------------- #
    story += [P("Part 2 &mdash; Proposed Architecture", H_PART)]

    story += [P("2.1 Synchronization &mdash; Optimistic Locking with Versioning", H_SUB)]
    story += [P(
        "Add a monotonic <i>version</i> column to <i>documents</i>. Every read "
        "returns the version; every write sends it back as a precondition. The "
        "server commits with a single atomic compare-and-swap:"
    )]
    story += [P(
        "<font face='Courier' size='8.5'>"
        "UPDATE documents SET body=:b, version=version+1 "
        "WHERE id=:id AND version=:client_version;"
        "</font>"
    )]
    story += [P(
        "If <i>rowcount=0</i>, the row was changed by someone else &rarr; respond "
        "<b>409 Conflict</b> with the current server version; the client refetches, "
        "merges (3-way diff or OT/CRDT for collaborative editors), and retries. "
        "Pessimistic locking (<i>SELECT FOR UPDATE</i>) would also work but holds "
        "DB locks across user think-time, so it scales worse and creates "
        "head-of-line blocking. Optimistic locking is wait-free in the common case."
    )]

    story += [SequenceDiagram()]
    story += [P(
        "Figure 1. UML sequence diagram for the optimistic-locking sync fix. "
        "Both clients read version&nbsp;42; Alice's CAS succeeds (rowcount=1) and "
        "the version becomes 43; Bob's stale CAS fails (rowcount=0) and the "
        "server returns 409 with the current version so the client can merge.",
        DIAG_CAPTION,
    )]

    story += [P("2.2 Coordination &mdash; Idempotent Inbox + Retries + DLQ", H_SUB)]
    story += [P(
        "Make webhook delivery <i>at-least-once</i> and processing <i>idempotent</i>:"
    )]
    story += [
        B("Clerk attaches a unique <i>Svix-Id</i> per event. The handler "
          "<b>INSERT</b>s it into a <i>webhook_inbox(svix_id PRIMARY KEY)</i> "
          "table inside the same transaction that applies the state change; on "
          "duplicate-key the handler short-circuits with 200 OK, so safe retries "
          "are free."),
        B("Persist the event to a durable queue (Postgres + <i>SKIP LOCKED</i>, "
          "Redis Streams, or RabbitMQ quorum queues) and <b>ack only after</b> the "
          "DB transaction commits. A worker pool drains the queue with bounded "
          "exponential backoff (e.g. 1 s, 5 s, 30 s, 5 min, &hellip;)."),
        B("After N attempts the message lands in a Dead Letter Queue and pages "
          "an operator. A nightly reconciliation job calls Clerk's billing API "
          "and repairs any drift &mdash; the convergence safety net."),
        B("End-to-end this is at-least-once delivery + idempotent application = "
          "effectively exactly-once for our state, without distributed transactions."),
    ]

    story += [P("2.3 Fault Tolerance &mdash; Circuit Breaker + Fallback", H_SUB)]
    story += [P(
        "Wrap the LLM client in a CLOSED &rarr; OPEN &rarr; HALF_OPEN circuit breaker:"
    )]
    story += [
        B("<b>Per-call timeout</b> (e.g. 2 s), independent of the upstream's 60 s "
          "socket timeout, so a single hung request never holds a worker hostage."),
        B("After K consecutive failures the breaker <b>OPENs</b> for T seconds; "
          "during that window every call <b>fails fast</b> with no upstream I/O "
          "&mdash; the broken dependency is isolated."),
        B("After T elapses, one probe is admitted in <b>HALF_OPEN</b>; success "
          "&rarr; CLOSED, failure &rarr; OPEN again. This prevents a thundering "
          "herd from re-killing a recovering upstream."),
        B("On every failure path the handler returns a <b>fallback</b> "
          "(cached prior answer, smaller local model, or templated &ldquo;tutor "
          "is degraded&rdquo; message) instead of bubbling the exception."),
        B("Optionally pair with a <b>bulkhead</b> (semaphore on concurrent LLM "
          "calls) so the LLM cannot starve unrelated endpoints' workers."),
    ]
    story += [P(
        "This is the pattern implemented in <i>app/circuit_breaker.py</i> and "
        "verified by <i>tests/test_circuit_breaker.py</i>."
    )]

    story += [P("2.4 CAP / PACELC Trade-offs", H_SUB)]
    story += [P(
        "Partition tolerance is non-negotiable in a real system, so per Brewer's "
        "theorem each component is really a choice between Consistency and "
        "Availability; PACELC adds a Latency vs Consistency axis when no partition "
        "is happening. The proposed architecture deliberately picks differently "
        "in different places:"
    )]
    story += [
        B("<b>Sync fix &mdash; CP / PC.</b> We pick Consistency: concurrent writers "
          "may be rejected with 409 (a small Availability hit on the write path) "
          "to guarantee no lost update. The latency cost is one extra SQL "
          "predicate, which is negligible. This is the right call for "
          "user-authored data, where silent corruption is unacceptable."),
        B("<b>Coordination fix &mdash; AP / EL.</b> The auth provider and our DB "
          "may briefly disagree during a retry storm. We accept that bounded "
          "staleness in exchange for staying available during partitions; the "
          "idempotent inbox + DLQ + nightly reconciliation guarantee eventual "
          "convergence. Webhook latency rises slightly (extra DB writes per "
          "event), which is fine because no human is waiting on it."),
        B("<b>Fault-tolerance fix &mdash; AP / EL.</b> When the LLM is unhealthy "
          "we serve a stale or templated answer rather than block the user. We "
          "trade strict freshness for a 200 ms response instead of a 60 s hang "
          "and a process-wide outage. From the user's perspective this is a "
          "massive Availability and Latency win at the cost of correctness on a "
          "single, non-critical code path."),
    ]
    story += [P(
        "Net architectural philosophy: <b>CP at the core data plane, AP at the "
        "edges</b> (third-party integrations, ML calls). This matches how "
        "production systems at scale (Stripe, GitHub, Netflix) are actually built."
    )]

    doc.build(story)
    print(f"wrote {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
