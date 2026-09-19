"""Feature 21 — tamper-evident report fingerprint."""
import hashlib, json

def make_fingerprint(result: dict, address: str) -> str:
    payload = {
        "address": address,
        "score": result["score"],
        "band": result.get("band"),
        "risk": result["risk_label"],
        "items": [{"t": i["title"], "s": i["status"]} for i in result["items"]],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return "EMB-" + digest[:8].upper() + "-" + digest[8:12].upper()