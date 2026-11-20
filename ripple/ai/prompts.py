"""Prompts and output shapes for the three AI jobs (from the build plan, lightly refined).

Each job returns JSON that code checks before anything is saved. The JSON
schemas below are sent to Claude as "structured outputs", so the reply is
guaranteed to have the right shape; code then checks the content (quotes
appear word for word, companies are on the map, impacts sit on real paths).
"""

# ---------------------------------------------------------------- Job 1 ----
LINK_EXTRACTOR_SYSTEM = """You read company filings and pull out supply chain relationships.
You only report what the text itself states. You never add outside knowledge.
Filings may be in English, Korean or Japanese; always answer in English, but copy quotes in the
original language exactly as written."""

LINK_EXTRACTOR_USER = """Company that filed: {company_name}
Document: {doc_type}, {published_at}
Section: {section}
Text:
<<<
{section_text}
>>>

List every relationship the text states between the filing company and another
organization, place, or material. Use only these types:
- supplies: one company sells goods or services to another
- makes_in: the company produces in a named country, region or site
- uses: the company depends on a named material or part
- produces: the company makes a named material or part

Rules:
- Only include relationships the text actually states. Do not use outside knowledge.
- "quote" must be copied word for word from the text, one or two sentences. Do not fix typos,
  shorten, or join sentences from different places.
- "direction" says which way a "supplies" link goes: filer_to_other means the filer sells to the other
  party; other_to_filer means the other party sells to the filer. For makes_in, uses and produces use
  filer_to_other.
- If the text gives a share (for example "accounted for 18% of revenue"), put the number in "share"
  (18). Otherwise null.
- If the other party is unnamed ("a major customer", "Customer A"), set "other_party" to null and
  still include it.
- If there are no relationships, return an empty list."""

LINK_EXTRACTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["supplies", "makes_in", "uses", "produces"]},
                    "direction": {"type": "string", "enum": ["filer_to_other", "other_to_filer"]},
                    "other_party": {"type": ["string", "null"]},
                    "what": {"type": ["string", "null"]},
                    "share": {"type": ["number", "null"]},
                    "quote": {"type": "string"},
                },
                "required": ["type", "direction", "other_party", "what", "share", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["links"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------- Job 2 ----
EVENT_CHECKER_SYSTEM = """You decide whether a news item is a real supply chain event for AI hardware.
Opinion pieces, stock commentary, price targets and previews are never events."""

EVENT_CHECKER_USER = """Map nodes mentioned (id: name): {matched_nodes}
Item:
<<<
{headline_and_summary}
>>>

Answer:
- is_event: true only if something actually changed supply, demand, capacity, prices or rules for
  these nodes (not opinion pieces, not stock commentary).
- event_type: disruption | shortage | new_contract | policy | price_spike | capacity_change (null if not an event)
- severity: 1 (minor, local, short) to 5 (major, global, months) (null if not an event)
- affected_nodes: ids of the mentioned nodes that are directly hit (only ids from the list above)
- one_line: a plain one-sentence description"""

EVENT_CHECKER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_event": {"type": "boolean"},
        "event_type": {"type": ["string", "null"], "enum": ["disruption", "shortage", "new_contract", "policy",
                                                            "price_spike", "capacity_change", None]},
        "severity": {"type": ["integer", "null"]},
        "affected_nodes": {"type": "array", "items": {"type": "string"}},
        "one_line": {"type": "string"},
    },
    "required": ["is_event", "event_type", "severity", "affected_nodes", "one_line"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------- Job 3 ----
RIPPLE_EXPLAINER_SYSTEM = """You are a supply chain analyst. You explain how an event travels through a
supply map to the companies it reaches, for readers who are not experts. You describe exposure,
never trades: no buy, sell, hold, price targets or investment advice."""

RIPPLE_EXPLAINER_USER = """An event has happened. Code has already traced every path from the event
through our supply map and scored each company's exposure. Your job is to judge and explain, using
only the evidence given.

Event: {event_title} ({event_type}, severity {severity}, {started_at})
Event sources:
{event_source_snippets}

Paths found (event -> ... -> company), with exposure score (0-100) and the source quote for every link:
{paths_with_scores_and_quotes}

For each company reached (use the company id exactly as written in brackets):
1. direction: hurt, helped (for example a competitor or alternative supplier), or unclear
2. how_much: low, medium or high, and why in one or two sentences ("why")
3. timing: when the effect would show up (weeks, a quarter, a year)
4. confidence: high, medium or low, and what the confidence rests on (put that inside "why")
5. what_would_change_this: one thing that would make this call wrong

Then write:
- summary: three to five plain sentences a non-expert can follow
- biggest_unknowns: the gaps in our map that matter most for this event

Rules:
- Only include companies from the list above. Do not add companies that are not listed.
- Use only the links and quotes provided. If you rely on general knowledge, say so in "why",
  set "uses_general_knowledge" to true, and set confidence to low.
- Do not give buy or sell advice. Describe exposure, not trades.
- If a path looks weak (low confidence links, tiny share), say it may not matter."""

RIPPLE_EXPLAINER_SCHEMA = {
    "type": "object",
    "properties": {
        "impacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "direction": {"type": "string", "enum": ["hurt", "helped", "unclear"]},
                    "how_much": {"type": "string", "enum": ["low", "medium", "high"]},
                    "why": {"type": "string"},
                    "timing": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "uses_general_knowledge": {"type": "boolean"},
                    "what_would_change_this": {"type": "string"},
                },
                "required": ["company", "direction", "how_much", "why", "timing", "confidence",
                             "uses_general_knowledge", "what_would_change_this"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
        "biggest_unknowns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["impacts", "summary", "biggest_unknowns"],
    "additionalProperties": False,
}
