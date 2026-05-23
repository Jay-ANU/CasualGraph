"""Short-term memory chatbot for ESG Knowledge Graph.

Memory design: sliding window (last 10 messages) + LLM summary for older turns.
Graph state injected per request so the LLM always knows what the user is viewing.

Integration point: team member chatbot code should call build_messages() to get
the full message list to pass to the LLM, then call update_memory() with the reply.
"""

import time
import uuid
from collections import deque

import anthropic

# ---------------------------------------------------------------------------
# In-memory session store  {session_id: SessionMemory}
# Sessions expire after 30 minutes of inactivity.
# ---------------------------------------------------------------------------
_sessions: dict[str, "SessionMemory"] = {}
SESSION_TTL = 1800  # seconds


class SessionMemory:
    MAX_RECENT = 10       # messages kept verbatim
    SUMMARISE_AFTER = 10  # trigger summary when recent hits this size

    def __init__(self):
        self.summary: str = ""
        self.recent: deque[dict] = deque(maxlen=self.MAX_RECENT)
        self.graph_state: dict = {}
        self.last_active: float = time.time()

    def touch(self):
        self.last_active = time.time()

    def add(self, role: str, content: str):
        self.recent.append({"role": role, "content": content})
        self.touch()

    def needs_summary(self) -> bool:
        return len(self.recent) >= self.SUMMARISE_AFTER

    def pop_oldest_for_summary(self, n: int = 6) -> list[dict]:
        """Remove and return the oldest n messages for summarisation."""
        popped = []
        for _ in range(min(n, len(self.recent))):
            popped.append(self.recent.popleft())
        return popped


def _get_session(session_id: str) -> SessionMemory:
    _expire_sessions()
    if session_id not in _sessions:
        _sessions[session_id] = SessionMemory()
    return _sessions[session_id]


def _expire_sessions():
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s.last_active > SESSION_TTL]
    for sid in expired:
        del _sessions[sid]


# ---------------------------------------------------------------------------
# Graph state → human-readable context string
# ---------------------------------------------------------------------------
def _graph_state_to_context(state: dict) -> str:
    if not state:
        return "No graph view active."

    view = state.get("view", "summary")
    companies = ", ".join(state.get("companies") or []) or "all companies"
    years = ", ".join(str(y) for y in (state.get("years") or [])) or "all years"

    lines = [f"Companies: {companies} | Years: {years}"]

    if view == "summary":
        lines.insert(0, "Viewing: Domain summary graph (Environmental / Social / Governance / AI)")
    elif view == "subcluster":
        domain = state.get("domain", "")
        lines.insert(0, f"Viewing: {domain.title()} domain — ontology community breakdown")
    elif view == "detail":
        domain = state.get("domain", "")
        community = state.get("community", "")
        label = f"{domain.title()} › {community}" if community else domain.title()
        lines.insert(0, f"Viewing: {label} — entity-level knowledge graph")
        entities = state.get("entities") or []
        if entities:
            sample = ", ".join(entities[:10])
            if len(entities) > 10:
                sample += f" … (+{len(entities)-10} more)"
            lines.append(f"Visible entities: {sample}")
    elif view == "crossdomain":
        d1 = state.get("domain", "")
        d2 = state.get("domain2", "")
        lines.insert(0, f"Viewing: Cross-domain community connections — {d1.title()} ↔ {d2.title()}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are an ESG Knowledge Graph analyst assistant. \
You help users explore and understand ESG (Environmental, Social, Governance) \
data extracted from corporate sustainability reports.

You can do two things:
1. Answer questions about the ESG data visible in the current graph.
2. Navigate the graph by responding with a JSON action block (see below).

Navigation actions — include as a fenced JSON block when the user asks to navigate:
```json
{{"action": "drillDown", "domain": "<environmental|social|governance|ai>"}}
{{"action": "drillCommunity", "domain": "<domain>", "community": "<community label>"}}
{{"action": "crossDomain", "domain1": "<domain>", "domain2": "<domain>"}}
{{"action": "filterYear", "years": [<year>, ...]}}
{{"action": "reset"}}
```

Be concise. When answering about ESG data, cite specific entities or triples when possible.\
"""


def _build_system(graph_state: dict) -> str:
    ctx = _graph_state_to_context(graph_state)
    return f"{_SYSTEM_PROMPT}\n\n[Current Graph View]\n{ctx}"


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------
def _summarise(client: anthropic.Anthropic, existing_summary: str, messages: list[dict]) -> str:
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    prompt = "Summarise the following conversation segment in 3-5 sentences, " \
             "preserving key facts, entities mentioned, and user intent.\n\n"
    if existing_summary:
        prompt += f"Existing summary:\n{existing_summary}\n\nNew segment to incorporate:\n{transcript}"
    else:
        prompt += transcript

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def build_messages(session: SessionMemory) -> list[dict]:
    """Assemble the full message list to send to the LLM."""
    messages = []
    if session.summary:
        messages.append({
            "role": "user",
            "content": f"[Conversation summary so far]\n{session.summary}",
        })
        messages.append({
            "role": "assistant",
            "content": "Understood, I have the context from our earlier conversation.",
        })
    messages.extend(session.recent)
    return messages


def chat(
    session_id: str,
    user_message: str,
    graph_state: dict,
    anthropic_api_key: str,
) -> tuple[str, str]:
    """Process one user turn. Returns (reply, session_id)."""
    if not session_id:
        session_id = str(uuid.uuid4())

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    session = _get_session(session_id)
    session.graph_state = graph_state

    # Summarise older turns if window is full
    if session.needs_summary():
        old_messages = session.pop_oldest_for_summary(6)
        session.summary = _summarise(client, session.summary, old_messages)

    session.add("user", user_message)
    messages = build_messages(session)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_build_system(graph_state),
        messages=messages,
    )
    reply = response.content[0].text.strip()
    session.add("assistant", reply)

    return reply, session_id
