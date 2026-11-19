"""Generate extended contracts; frozen v1 files are inputs, never rewritten."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cache = load("contracts_cache", "lib/observation/inspection_cache.py")
verify = load("contracts_verify", "lib/verify_snapshot.py")
findings = load("contracts_findings", "lib/observation/findings.py")
obj, integer, text = verify.inspect.object_schema, verify.inspect.integer_schema, verify.inspect.text_schema
hash_value = text(r"[0-9a-f]{64}", False)
timestamp = {"type": "number", "minimum": 0, "maximum": 253402300799}
observed = {"type": "string", "format": "date-time"}
name = text(r"[a-z0-9][a-z0-9._-]{0,31}", False)
uuid = text(verify.inspect.UUID, False)
snapshot = verify.inspect.contract()


def write(kind, version, schema):
    schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "title": kind + "/" + version})
    path = ROOT / "schemas" / kind / (version + ".schema.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def nullable(rule):
    return {"anyOf": [rule, {"type": "null"}]}


baseline = obj({"schema": {"const": "baseline/v1"}, "source": {"const": "LOCAL_ACCEPTED"}, "endpoint": hash_value,
                "snapshot": snapshot, "snapshot_sha256": hash_value, "accepted_at": timestamp, "baseline_sha256": hash_value})
write("baseline", "v1", baseline)
meta = obj({"source": {"const": "LOCAL_ACCEPTED"}, "accepted_at": timestamp, "baseline_sha256": hash_value,
            "snapshot_sha256": hash_value, "instance_id": uuid, "observed_at": observed})
item = obj({"name": name, "node_id": uuid, "instance_id": nullable(uuid), "state": {"enum": ["OK", "PARTIAL", "UNKNOWN"]},
            "reason": {"enum": list(cache.REASONS)}, "observed_at": nullable(observed), "snapshot_sha256": nullable(hash_value),
            "baseline": nullable(meta), "snapshot": nullable(snapshot), "drift": obj({"state": {"enum": ["MATCH", "DRIFT", "UNKNOWN"]},
            "checks": obj({k: obj({"state": {"enum": ["MATCH", "DRIFT", "UNKNOWN"]}, "changed_count": integer(128, False)}) for k in cache.COMPONENTS})})})
write("inspect-cache", "v1", obj({"schema": {"const": "inspect-cache/v1"}, "cache_state": {"enum": ["EMPTY", "OK", "PARTIAL", "CACHE_CORRUPT"]},
                                   "nodes": {"type": "array", "maxItems": 1024, "items": item}, "truncated": {"type": "boolean"}}))
write("verify", "v2", verify.contract())
write("fleet-verify", "v2", obj({"schema": {"const": "fleet-verify/v2"}, "nodes": {"type": "array", "maxItems": 1024,
      "items": obj({"name": name, "state": {"enum": ["OK", "ERROR", "AUTH_FAILED", "TIMEOUT", "UNSUPPORTED"]}, "snapshot": nullable(verify.contract())})}}))
for kind in ("findings", "timeline"):
    schema = json.loads((ROOT / "schemas" / kind / "v1.schema.json").read_text(encoding="utf-8"))
    schema["properties"]["schema"]["const"] = kind + "/v2"
    def extend(rule):
        if isinstance(rule, dict):
            if "enum" in rule:
                enum = rule["enum"]
                if "AUDIT_STALLED" in enum:
                    enum.extend(findings.DRIFT_TYPES)
                elif "audit" in enum:
                    enum.append("drift")
                elif findings.TYPES["AUDIT_STALLED"][2] in enum:
                    enum.extend(v[2] for v in findings.DRIFT_TYPES.values())
            if rule.get("propertyNames", {}).get("enum") and "poll_age_seconds" in rule["propertyNames"]["enum"]:
                rule["propertyNames"]["enum"].append("changed_count")
            if "properties" in rule and "AUDIT_STALLED" in rule["properties"]:
                for typ in findings.DRIFT_TYPES:
                    rule["properties"][typ] = copy.deepcopy(rule["properties"]["AUDIT_STALLED"])
            for child in list(rule.values()):
                extend(child)
        elif isinstance(rule, list):
            for child in rule:
                extend(child)
    extend(schema)
    schema["$defs"]["evidence"]["properties"]["changed_count"] = {"$ref": "#/$defs/evidenceValue"}
    for typ, (category, severity, explanation) in findings.DRIFT_TYPES.items():
        schema["$defs"]["finding"]["allOf"].append({"if": {"properties": {"type": {"const": typ}}}, "then": {"properties": {
            "category": {"const": category}, "severity": {"const": severity}, "explanation": {"const": explanation}, "subject": {"$ref": "#/$defs/nodeSubject"}}}})
    if kind == "timeline":
        event = obj({"id": hash_value, "at": timestamp, "kind": {"enum": ["BASELINE_ACCEPTED", "BASELINE_CLEARED"]},
                     "subject": schema["$defs"]["nodeSubject"], "detail": obj({"source": {"const": "LOCAL_ACCEPTED"}, "snapshot_sha256": hash_value, "baseline_sha256": hash_value})})
        schema["properties"]["events"]["items"]["anyOf"].append(event)
    write(kind, "v2", schema)
schema = json.loads((ROOT / "schemas/monitor/v2.schema.json").read_text(encoding="utf-8"))
schema["properties"]["schema"]["const"] = "monitor/v3"
schema["properties"]["run"]["required"].append("inspection_write_errors")
schema["properties"]["run"]["properties"]["inspection_write_errors"] = {"type": "integer", "minimum": 0}
write("monitor", "v3", schema)
