import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("audit_tracing", Path(__file__).with_name("audit_tracing.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class TraceAuditTests(unittest.TestCase):
    def rows(self):
        return [
            {"id": "root", "traceId": "synthetic", "name": "chat-response", "type": "SPAN",
             "parentObservationId": None, "input": "REDACTED", "output": "REDACTED"},
            {"id": "first", "name": "generate-response", "type": "GENERATION", "parentObservationId": "root",
             "input": "REDACTED", "output": "REDACTED", "model": "fake", "usageDetails": {"input": 11, "output": 3}},
            {"id": "tool", "name": "read_page", "type": "TOOL", "parentObservationId": "root",
             "input": "REDACTED", "output": "REDACTED"},
            {"id": "second", "name": "generate-response", "type": "GENERATION", "parentObservationId": "root",
             "input": "REDACTED", "output": "REDACTED", "model": "fake", "usageDetails": {"input": 23, "output": 7}},
        ]

    def test_inspection_requires_redacted_complete_nested_model_tool_trace(self):
        result = audit.inspect_trace(self.rows(), {"message": "sentinel-message", "file": "sentinel-file"})
        self.assertTrue(result["all_content_markers_absent"])
        self.assertEqual(result["tools"], ["read_page"])
        for mutation in ["parent", "usage", "model", "tool", "io"]:
            rows = self.rows()
            if mutation == "parent":
                rows[1]["parentObservationId"] = "absent"
            elif mutation == "usage":
                rows[1]["usageDetails"] = {}
            elif mutation == "model":
                rows[1]["model"] = None
            elif mutation == "tool":
                rows[2]["name"] = "wrong-tool"
            else:
                rows[2]["output"] = "not masked"
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit.inspect_trace(rows, {"file": "sentinel-file"})

    def test_inspection_rejects_file_sentinel_in_nested_metadata(self):
        rows = self.rows()
        rows[2]["metadata"] = {"nested": {"source": "long prefix " * 40 + "sentinel-file"}}
        with self.assertRaisesRegex(AssertionError, "leaked"):
            audit.inspect_trace(rows, {"file": "sentinel-file"})

    def test_api_queries_expand_metadata_and_follow_cursor(self):
        def envelope(rows, cursor=None):
            return json.dumps({"status": 200, "body": {"data": rows, "meta": {"cursor": cursor}}}).encode()
        responses = [
            envelope([{"id": "1", "metadata": {"nested": "truncated"}}], "next"),
            envelope([{"id": "1", "metadata": {"nested": "complete"}}], "next"),
            envelope([{"id": "2", "metadata": {}}]),
        ]
        with patch.object(audit, "execute", side_effect=responses) as execute:
            rows = audit.observations({}, trace_id="synthetic")
        self.assertEqual([row["id"] for row in rows], ["1", "2"])
        self.assertEqual(rows[0]["metadata"]["nested"], "complete")
        self.assertIn("--expand-metadata", execute.call_args_list[1].args[0])
        self.assertIn("--cursor", execute.call_args_list[2].args[0])
        with patch.object(audit, "execute", return_value=json.dumps({"status": 401, "body": {}}).encode()):
            with self.assertRaises(RuntimeError):
                audit.observations({})

    def test_live_audit_requires_explicit_opt_in_before_network_or_writes(self):
        with patch.dict(os.environ, {"AUDIT_LIVE_TRACING": ""}), patch.object(audit, "execute") as execute:
            with self.assertRaisesRegex(RuntimeError, "AUDIT_LIVE_TRACING"):
                audit.audit(120)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
