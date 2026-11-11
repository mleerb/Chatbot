import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
FIELDS = "core,basic,time,io,metadata,model,usage,prompt,metrics,trace_context"


def timestamp():
    return datetime.now(UTC).isoformat()


def execute(arguments, *, input=None, env=None, timeout=180):
    result = subprocess.run(arguments, cwd=ROOT, input=input, capture_output=True,
                            env=env, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("Audit subprocess failed; private output withheld")
    return result.stdout


def worker(run_id, control=False):
    if control:
        from app.core import trace
        with trace.trace_chat_turn(session_id=run_id, question="Synthetic acceptance exporter control",
                                   model="synthetic-acceptance", has_document=False) as (_, span):
            span.update(output="Synthetic acceptance control completed")
            identifier = span.trace_id
        trace.flush_traces()
        trace.get_tracing_client().shutdown()
        return {"trace_id": identifier}

    os.environ["LANGFUSE_TRACE_CONTENT"] = "false"
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = "acceptance"
    os.environ["WORKSPACE_EXPORT_ENABLED"] = "false"
    os.environ["WORKSPACE_EXPORT_GUESTS"] = "false"
    os.environ["EMBEDDING_MODEL"] = ""
    from deepagents import create_deep_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    from app.core import trace
    from app.services.agent import answer_question, stream_answer
    from app.services.sessions import ChatSession, Page, Upload, sessions, sessions_lock
    from app.tools.pages import create_page_tools

    markers = {kind: f"ASTER_ACCEPTANCE_{kind.upper()}_{run_id}" for kind in ("message", "file", "answer")}
    seen = {"message": False, "file": False, "tool_result": False}

    class SyntheticModel(FakeMessagesListChatModel):
        model_name: str = "synthetic-acceptance"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            text = str(messages)
            seen["message"] |= markers["message"] in text
            seen["file"] |= markers["file"] in text
            seen["tool_result"] |= any(getattr(message, "type", "") == "tool" and markers["file"] in str(message.content)
                                       for message in messages)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            message = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs).generations[0].message
            yield ChatGenerationChunk(message=AIMessageChunk(
                content=message.content, tool_calls=message.tool_calls,
                usage_metadata=message.usage_metadata, response_metadata=message.response_metadata,
            ))

    session = ChatSession(user_id=987654321, conversation_id=987654321, account={"id": 987654321})
    document = markers["file"] + "\n" + "Synthetic page text for the acceptance audit. " * 700
    item = Upload(filename="synthetic-acceptance.txt", data=document.encode(), document=document,
                  image_url="", status="Synthetic acceptance fixture",
                  pages=[Page(label="1", text=document)])
    session.uploads[item.id] = item
    with sessions_lock:
        sessions[run_id] = session
    identifiers = []
    try:
        def agent():
            model = SyntheticModel(responses=[
                AIMessage(content="", tool_calls=[{"name": "read_page", "args": {"page": 1, "file_id": item.id},
                                                   "id": "synthetic-read-page"}],
                          usage_metadata={"input_tokens": 11, "output_tokens": 3, "total_tokens": 14},
                          response_metadata={"model_name": "synthetic-acceptance"}),
                AIMessage(content=markers["answer"] + " " + markers["file"],
                          usage_metadata={"input_tokens": 23, "output_tokens": 7, "total_tokens": 30},
                          response_metadata={"model_name": "synthetic-acceptance"}),
            ])
            return create_deep_agent(model=model, tools=create_page_tools(run_id), system_prompt="Synthetic acceptance only")

        result = answer_question(agent(), markers["message"], [], run_id, [item], traces=identifiers, trace_session=run_id)
        assert markers["file"] in result and all(seen.values())
        events = list(stream_answer(agent(), markers["message"], [], run_id, [item], traces=identifiers,
                                    trace_session=run_id))
        assert any(event.get("type") == "text" and markers["answer"] in event.get("text", "") for event in events)
        guest_traces = []
        answer_question(agent(), markers["message"], [], run_id, [item], trace=False, traces=guest_traces)
        assert guest_traces == []
        assert len(identifiers) == 2
        trace.flush_traces()
        trace.get_tracing_client().shutdown()
        return {"trace_ids": identifiers, "session_id": run_id, "markers": markers,
                "model_received": seen, "guest_trace_ids": guest_traces,
                "streamed_output_seen": True, "content_setting": False}
    finally:
        with sessions_lock:
            sessions.pop(run_id, None)


def cli_environment():
    code = "import json,os; print(json.dumps({k:os.getenv(k,'') for k in ('LANGFUSE_PUBLIC_KEY','LANGFUSE_SECRET_KEY','LANGFUSE_BASE_URL','LANGFUSE_TRACE_CONTENT')}))"
    values = json.loads(execute(["docker", "compose", "exec", "-T", "app", "python", "-c", code]))
    if not all(values[key] for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
        raise RuntimeError("Live tracing credentials are not configured")
    return {**os.environ, **values, "LANGFUSE_HOST": values["LANGFUSE_BASE_URL"]}, values["LANGFUSE_TRACE_CONTENT"]


def observations(env, **filters):
    arguments = ["npx", "--yes", "langfuse-cli@1.3.1", "api", "observations", "list", "--json", "--fields", FIELDS,
                 "--limit", "1000"]
    rows = []
    cursor = None
    while True:
        query = arguments + [part for key, value in filters.items() for part in ("--" + key.replace("_", "-"), str(value))]
        if cursor:
            query += ["--cursor", cursor]
        envelope = json.loads(execute(query, env=env))
        if "body" in envelope:
            if envelope.get("status") != 200:
                raise RuntimeError("Observations API returned a non-success status")
            envelope = envelope["body"]
        if "data" in envelope and isinstance(envelope["data"], dict):
            envelope = envelope["data"]
        batch = envelope.get("data")
        if not isinstance(batch, list):
            raise ValueError("Unexpected observations response envelope")
        metadata_keys = sorted({key for row in batch for key in (row.get("metadata") or {})})
        if metadata_keys:
            expanded = json.loads(execute(query + ["--expand-metadata", ",".join(metadata_keys)], env=env))
            if expanded.get("status") != 200 or not isinstance(expanded.get("body", {}).get("data"), list):
                raise ValueError("Full metadata expansion failed")
            envelope = expanded["body"]
            batch = envelope["data"]
        rows.extend(batch)
        cursor = envelope.get("meta", {}).get("cursor")
        if not cursor:
            return rows
        if len(rows) >= 5000:
            raise ValueError("Observation safety cap exceeded; narrow the audit window")


def invoke_worker(run_id, control=False):
    source = Path(__file__).read_bytes()
    arguments = ["docker", "compose", "exec", "-T", "app", "python", "-", "--worker", run_id]
    if control:
        arguments.append("--control")
    return json.loads(execute(arguments, input=source))


def wait_for_trace(env, identifier):
    for _ in range(12):
        rows = observations(env, trace_id=identifier)
        if rows:
            return rows
        time.sleep(5)
    raise RuntimeError("Exported trace was not visible within the bounded ingestion window")


def inspect_trace(rows, markers):
    serialized = json.dumps(rows, ensure_ascii=False)
    if any(marker in serialized for marker in markers.values()):
        raise AssertionError("Synthetic content leaked in exported observation fields")
    ids = {row["id"] for row in rows}
    roots = [row for row in rows if not row.get("parentObservationId")]
    assert len(roots) == 1 and roots[0]["name"] == "chat-response"
    assert all(not row.get("parentObservationId") or row["parentObservationId"] in ids for row in rows)
    assert not {"PatchToolCallsMiddleware.before_agent", "_ParentNotifierMiddleware.after_agent"}.intersection(row["name"] for row in rows)
    generations = [row for row in rows if row["type"] == "GENERATION"]
    tools = [row for row in rows if row["type"] == "TOOL"]
    assert len(generations) == 2 and all(row["name"] == "generate-response" for row in generations)
    assert [row["name"] for row in tools] == ["read_page"]
    assert all(row.get("model") for row in generations)
    assert sum(row.get("usageDetails", {}).get("input", 0) for row in generations) == 34
    assert sum(row.get("usageDetails", {}).get("output", 0) for row in generations) == 10
    assert "REDACTED" in serialized
    assert all("REDACTED" in str(row.get("input")) and "REDACTED" in str(row.get("output")) for row in [roots[0], *generations, *tools])
    return {"trace_id": roots[0]["traceId"], "observations": len(rows), "generations": len(generations),
            "tools": [row["name"] for row in tools], "model": generations[0]["model"],
            "usage": {"input": 34, "output": 10, "synthetic": True}, "all_parents_present": True,
            "all_content_markers_absent": True, "metadata_values_expanded": True,
            "root_model_tool_io_redacted": True,
            "names": sorted(row["name"] for row in rows)}


def audit(health_seconds):
    if os.getenv("AUDIT_LIVE_TRACING") != "1":
        raise RuntimeError("Set AUDIT_LIVE_TRACING=1 to export synthetic traces and query live observations")
    run_id = uuid4().hex
    output = ROOT / ".workspace" / "acceptance" / run_id
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    for parent in (output.parent.parent, output.parent):
        if parent.is_symlink() or parent.stat().st_mode & 0o077:
            raise ValueError("Audit output directory must be private and not a symlink")
    output.mkdir(mode=0o700)
    env, live_content = cli_environment()
    report = {"version": 1, "run_id": run_id, "started_at": timestamp(), "live_content_setting_before": live_content,
              "provider_calls": 0, "production_history_writes": 0}
    print("Running isolated redacted tool/stream paths and checking Langfuse observations...", flush=True)
    result = invoke_worker(run_id)
    report["execution"] = {key: value for key, value in result.items() if key != "markers"}
    report["traces"] = []
    for identifier in result["trace_ids"]:
        wait_for_trace(env, identifier)
        time.sleep(5)
        report["traces"].append(inspect_trace(observations(env, trace_id=identifier), result["markers"]))
    session_rows = observations(env, session_id=run_id)
    assert {row["traceId"] for row in session_rows} == set(result["trace_ids"])
    print("Redaction passed; checking bounded live health window...", flush=True)
    before = invoke_worker(run_id + "-before", control=True)
    wait_for_trace(env, before["trace_id"])
    start = timestamp()
    health_code = "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=10).status)"
    checks = []
    deadline = time.monotonic() + health_seconds
    while time.monotonic() < deadline:
        checks.append(execute(["docker", "compose", "exec", "-T", "app", "python", "-c", health_code]).decode().strip())
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(30, remaining))
    end = timestamp()
    after = invoke_worker(run_id + "-after", control=True)
    wait_for_trace(env, after["trace_id"])
    time.sleep(10)
    rows = observations(env, from_start_time=start, to_start_time=end)
    report["health"] = {"from": start, "to": end, "seconds": health_seconds, "explicit_statuses": checks,
                        "observations_in_window": len(rows), "control_trace_ids": [before["trace_id"], after["trace_id"]],
                        "control_export_visible_before_and_after": True}
    assert all(status == "200" for status in checks) and not rows
    _, after_content = cli_environment()
    report["live_content_setting_after"] = after_content
    assert after_content == live_content
    report["completed_at"] = timestamp()
    descriptor = os.open(output / "report.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(report, stream, indent=2)
    print(f"Final tracing acceptance passed. Private report: {output / 'report.json'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--control", action="store_true")
    parser.add_argument("--health-seconds", type=int, default=120)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, args.control)))
    else:
        if args.health_seconds < 120:
            parser.error("Health acceptance window must be at least 120 seconds")
        audit(args.health_seconds)


if __name__ == "__main__":
    main()
