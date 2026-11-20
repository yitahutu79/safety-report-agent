"""JSON Schema for Ollama constrained decoding; factual checks remain independent."""

def report_unit_schema(headings, evidence):
    text = {"type": "string"}
    def array(item): return {"type": "array", "items": item}
    def obj(props): return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    heading = {"type": "string", "enum": headings} if headings else text
    ids = [e["id"] for e in evidence if isinstance(e.get("id"), str)]
    citation = {"type": "string", "enum": ids} if ids else text
    return obj({
        "editorial_plan": array(obj({"decision": {"type": "string", "enum": ["use", "omit", "verify"]},
            "topic": text, "summary": text, "evidence_ids": array(citation)})),
        "paragraphs": array(obj({"heading": heading, "text": text, "evidence_ids": array(citation)})),
        "tables": array(obj({"heading": heading, "caption": text, "headers": array(text),
            "rows": array(array(text)), "evidence_ids": array(citation)})),
        "missing": array(text), "review": array(text)})
