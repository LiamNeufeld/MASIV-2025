import os
import re
import json
import requests

HF_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")
# A small, free model endpoint (text2text) usually available in the free tier.
HF_MODEL = os.environ.get("HF_MODEL", "google/flan-t5-base")
HF_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

HEADERS = {"Authorization": f"Bearer {HF_API_KEY}"} if HF_API_KEY else {}

def _basic_rule_parser(q: str):
    """Very small rule-based fallback to ensure we always return something usable."""
    ql = q.lower()
    filters = []

    # money filters like "< $500,000", "under 700k"
    money = re.search(r'(\$?\s*\d[\d,\.]*\s*(k|m)?)', ql)
    if "less than" in ql or "under" in ql or "<" in ql:
        if money:
            val = money.group(1).replace("$", "").replace(",", "").strip()
            if val.endswith("k"):
                num = float(val[:-1]) * 1_000
            elif val.endswith("m"):
                num = float(val[:-1]) * 1_000_000
            else:
                num = float(val)
            filters.append({"attribute": "assessed_value", "operator": "<", "value": num, "unit": "$"})
    if "greater than" in ql or "over" in ql or "more than" in ql or ">" in ql:
        if money:
            val = money.group(1).replace("$", "").replace(",", "").strip()
            if val.endswith("k"):
                num = float(val[:-1]) * 1_000
            elif val.endswith("m"):
                num = float(val[:-1]) * 1_000_000
            else:
                num = float(val)
            filters.append({"attribute": "assessed_value", "operator": ">", "value": num, "unit": "$"})

    # zoning codes like RC-G, R-C2, C-COR, etc.
    zoning = re.findall(r'\b([a-z]{1,3}-?[a-z0-9]{1,4})\b', ql)
    zoning = [z.upper() for z in zoning if any(c.isdigit() for c in z) or '-' in z]
    if zoning:
        filters.append({"attribute": "zoning", "operator": "in", "value": zoning})

    # height in feet/meters
    h = re.search(r'(?:over|greater than|>|under|less than|<)\s*(\d+)\s*(feet|foot|ft|meters|metres|m)', ql)
    if h:
        num = float(h.group(1))
        unit = h.group(2)
        if unit in ("feet", "foot", "ft"):
            # convert feet to meters
            num = num * 0.3048
        op = ">" if any(x in ql for x in ["over", "greater than", ">"]) else "<"
        filters.append({"attribute": "height_m", "operator": op, "value": num, "unit": "m"})

    # communities (very naive)
    if "downtown" in ql:
        filters.append({"attribute": "community", "operator": "=", "value": "Downtown"})
    return filters or [{"attribute": "assessed_value", "operator": ">", "value": 0, "unit": "$", "note": "fallback"}]

def parse_filter_with_llm(query: str):
    """
    Ask a free HF model to produce a JSON list of simple filters.
    If the call fails or output isn't JSON, use the rule-based parser.
    """
    prompt = (
        "You are a filter extractor for a city map. "
        "Given a natural language query, produce a JSON array of filters. "
        "Allowed attributes: assessed_value (number, $), height_m (number, meters), zoning (string or list), community (string). "
        "Allowed operators: >, <, =, in. "
        "Examples:\n"
        "Query: highlight buildings over 100 feet\n"
        '[{"attribute":"height_m","operator":">","value":30.48,"unit":"m"}]\n'
        "Query: show buildings in RC-G zoning\n"
        '[{"attribute":"zoning","operator":"in","value":["RC-G"]}]\n'
        "Query: show buildings less than $500,000 in value\n"
        '[{"attribute":"assessed_value","operator":"<","value":500000,"unit":"$"}]\n'
        "Now process this query:\n"
        f"Query: {query}\n"
        "Output only valid JSON:"
    )

    if not HF_API_KEY:
        return _basic_rule_parser(query)

    try:
        resp = requests.post(HF_URL, headers=HEADERS, json={"inputs": prompt, "options": {"wait_for_model": True}}, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        # HF text2text returns [{"generated_text": "..."}] sometimes; text-generation returns [{"generated_text": "..."}]
        if isinstance(data, list) and data and "generated_text" in data[0]:
            txt = data[0]["generated_text"]
        elif isinstance(data, dict) and "generated_text" in data:
            txt = data["generated_text"]
        else:
            # Try common key paths
            txt = json.dumps(data)
        # Attempt to locate JSON substring
        start = txt.find("[")
        end = txt.rfind("]")
        if start != -1 and end != -1 and end > start:
            js = txt[start:end+1]
            filters = json.loads(js)
            # sanity check
            if isinstance(filters, list):
                return filters
    except Exception:
        pass

    return _basic_rule_parser(query)
