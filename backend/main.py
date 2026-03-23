"""FastAPI server — SSE streaming endpoint for the diagnostic chat."""

from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from common.chain_log import (
    bind_trace_id,
    chain_debug,
    new_trace_id,
    reset_trace_id,
    setup_logging,
)

# Import agents so they self-register on module load
import agents.log_analytics  # noqa: F401
import agents.jira_knowledge  # noqa: F401

from agents.orchestrator import orchestrate

setup_logging()

app = FastAPI(title="Maxus FOTA Diagnostic Backend")
log = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    user_message: str = body.get("message", "")
    scenario_id: str = body.get("scenarioId", "fota-diagnostic")
    history: list[dict] = body.get("history", [])

    async def event_generator():
        trace_token = bind_trace_id(new_trace_id())
        t0 = time.perf_counter()
        chain_debug(
            log,
            step="http.chat",
            event="SSE_BEGIN",
            scenario_id=scenario_id,
            user_len=len(user_message),
            history_turns=len(history),
        )
        event_count = 0
        try:
            async for event in orchestrate(user_message, scenario_id, history):
                event_count += 1
                yield {"data": json.dumps(event, ensure_ascii=False)}
        finally:
            chain_debug(
                log,
                step="http.chat",
                event="SSE_END",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                events_emitted=event_count,
            )
            reset_trace_id(trace_token)

    return EventSourceResponse(event_generator())


@app.get("/health")
async def health():
    from agents.base import registry
    agents = [{"name": a.name, "display_name": a.display_name} for a in registry.all_agents()]
    return {"status": "ok", "agents": agents}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
