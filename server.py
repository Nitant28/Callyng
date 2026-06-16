import asyncio
import base64
import importlib
import json
import os
import re
import urllib.parse
import uuid
from contextlib import asynccontextmanager

import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from call_log_db import init_db
from db import postgres as pg_db
from plivo_hangup import handle_plivo_hangup
from telephony import build_hangup_url, make_plivo_call

load_dotenv(override=True)

# ── Select which bot to run ────────────────────────────────────────────────────
BOT_ROUTE = os.getenv("BOT_ROUTE", "sts")

# ── Module-level imports for the per-call hot path ────────────────────────────
# Importing the bot module and pipecat's WebSocketRunnerArguments at module
# load time (rather than inside the /ws handler) removes the tens-to-hundreds
# of microseconds of `import` machinery on every inbound WebSocket and ensures
# the lifespan pre-warm actually covers everything the hot path needs.
from pipecat.runner.types import WebSocketRunnerArguments  # noqa: E402

if BOT_ROUTE == "sts":
    from bot_sts import bot as _bot  # noqa: E402
else:
    from bot_cascade import bot as _bot  # noqa: E402

# ── Pre-warm state ─────────────────────────────────────────────────────────────
# Maps call_id → asyncio.Event that is set once Gemini is warmed up.
# The /answer route waits on this event before returning XML to Plivo,
# so by the time Plivo streams audio to /ws, Gemini is already connected.
_warmup_ready: dict[str, asyncio.Event] = {}


def _prewarm_live_connect_config():
    """Minimal LiveConnectConfig aligned with Pipecat audio STS (not empty setup)."""
    from google.genai.types import (
        AudioTranscriptionConfig,
        Content,
        LiveConnectConfig,
        Modality,
        Part,
        SpeechConfig,
        VoiceConfig,
    )
    from pipecat.services.google.gemini_live.llm import language_to_gemini_language

    model = os.getenv(
        "GEMINI_MODEL", "models/gemini-3.1-flash-live-preview"
    )
    voice = "Aoede"
    language = "mr-IN"

    if BOT_ROUTE == "sts":
        raw_script = (os.getenv("STS_SCRIPT") or "pyramid_mr").strip()
        if re.fullmatch(r"[a-z][a-z0-9_]*", raw_script):
            try:
                sts = importlib.import_module(f"sts_scripts.{raw_script}")
                model = getattr(
                    sts, "GEMINI_MODEL", model
                )
                voice = getattr(sts, "GEMINI_VOICE", voice)
                lang = getattr(sts, "GEMINI_LANGUAGE", None)
                if lang is not None:
                    mapped = language_to_gemini_language(lang)
                    if mapped:
                        language = mapped
            except ImportError as exc:
                logger.warning(
                    "[prewarm] STS script sts_scripts.{} not loaded ({}); using defaults",
                    raw_script,
                    exc,
                )

    config = LiveConnectConfig(
        response_modalities=[Modality.AUDIO],
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config={"voice_name": voice}
            ),
            language_code=language,
        ),
        input_audio_transcription=AudioTranscriptionConfig(),
        output_audio_transcription=AudioTranscriptionConfig(),
    )
    return model, config, Content, Part


async def _prewarm_gemini(call_id: str) -> None:
    """
    Open a real Gemini Live session, fire one dummy inference to eat the
    cold-start penalty, then signal the event so /answer can proceed.

    This runs as a background task started from /start, so the ~2-3 s
    Gemini cold-start happens while Plivo is being asked to place the call
    (which also takes ~1-2 s). By the time the callee picks up, Gemini is
    already warm.
    """
    if BOT_ROUTE != "sts":
        logger.debug(f"[prewarm:{call_id}] skipped (BOT_ROUTE={BOT_ROUTE!r})")
        event = _warmup_ready.get(call_id)
        if event:
            event.set()
        return

    from google import genai  # pip install google-genai  (NOT google-generativeai)

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning(f"[prewarm:{call_id}] GOOGLE_API_KEY missing; skipping prewarm")
        event = _warmup_ready.get(call_id)
        if event:
            event.set()
        return

    try:
        model, config, Content, Part = _prewarm_live_connect_config()
        logger.info(
            f"[prewarm:{call_id}] Connecting to Gemini Live model={model} …"
        )
        client = genai.Client(api_key=api_key)  # type: ignore[attr-defined]

        async with client.aio.live.connect(  # type: ignore[attr-defined]
            model=model, config=config
        ) as session:
            await session.send_client_content(
                turns=Content(role="user", parts=[Part(text="prewarm")]),
                turn_complete=True,
            )
            async for _ in session.receive():
                break

        logger.info(f"[prewarm:{call_id}] Gemini warmed up ✓")
    except Exception as exc:
        logger.warning(f"[prewarm:{call_id}] Pre-warm failed ({exc}); continuing anyway")
    finally:
        event = _warmup_ready.get(call_id)
        if event:
            event.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Pre-import heavy pipecat extras so the first /ws has zero import lag
    # The active bot module + WebSocketRunnerArguments are already imported at
    # module load (see top of file). Here we additionally warm up the optional
    # pipecat audio analyzers that ship native libs and ONNX models — the
    # first import of these can cost ~5–10 s when paid on the call hot path.
    logger.info("[startup] Pre-importing heavy pipecat audio modules …")
    try:
        from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnV3Analyzer  # noqa: F401
        from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: F401
        logger.info("[startup] Pre-import done — first call will have no import lag")
    except Exception as exc:
        logger.warning(f"[startup] Pre-import warning ({exc}); continuing anyway")

    db_path = os.getenv("CALL_LOG_DB_PATH", "./data/call_logs.db")
    try:
        init_db(db_path)
        logger.info(f"[startup] Call log DB ready at {db_path}")
    except Exception as exc:
        logger.warning(f"[startup] Call log DB init failed ({exc}); continuing without persistence")

    app.state.pool = None
    try:
        pool = await pg_db.init_pool()
        app.state.pool = pool
        if pool is not None:
            logger.info("[startup] PostgreSQL pool ready")
        else:
            logger.info("[startup] DATABASE_URL not set; PostgreSQL disabled")
    except Exception as exc:
        logger.warning(f"[startup] PostgreSQL pool init failed ({exc}); continuing without Postgres")

    app.state.dialer_tasks: dict[str, asyncio.Task] = {}
    app.state.session = aiohttp.ClientSession()
    app.state.stale_call_log_task = None
    if app.state.pool is not None:
        from dialer.maintenance import (
            run_stale_call_log_sweep,
            stale_call_log_loop,
            stale_call_log_sweep_enabled,
            stale_call_log_sweep_seconds,
        )

        if stale_call_log_sweep_enabled():
            try:
                await run_stale_call_log_sweep(pool)
            except Exception as exc:
                logger.warning("[startup] Stale call_log sweep failed: {}", exc)
            interval = stale_call_log_sweep_seconds()
            app.state.stale_call_log_task = asyncio.create_task(
                stale_call_log_loop(pool, interval)
            )
            logger.info(
                "[startup] Stale call_log sweep every {}s (grace {} min)",
                interval,
                pg_db.live_call_grace_minutes(),
            )
            
        # Auto-resume campaigns
        try:
            running_camps = await pg_db.get_all_running_campaigns(pool)
            if running_camps:
                from dialer.concurrent_dialer import start_dialer
                host = (os.getenv("DIALER_CALLBACK_HOST") or os.getenv("NGROK_URL") or "localhost:7860").strip()
                logger.info(f"[startup] Found {len(running_camps)} running campaigns. Auto-resuming...")
                for camp in running_camps:
                    start_dialer(app, camp["id"], camp["client_id"], host=host)
        except Exception as exc:
            logger.warning("[startup] Failed to auto-resume campaigns: {}", exc)
    yield
    stale_task = getattr(app.state, "stale_call_log_task", None)
    if stale_task is not None and not stale_task.done():
        stale_task.cancel()
        try:
            await stale_task
        except asyncio.CancelledError:
            pass
    await app.state.session.close()
    await pg_db.close_pool()


limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://admin.aakashvani.ai", "https://app.aakashvani.ai", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.post("/start")
async def start_call(request: Request) -> JSONResponse:
    """
    Trigger an outbound call with Gemini pre-warming.

    Body: { "phone_number": "+91XXXXXXXXXX", "body": { "lead_name": "Rahul" } }

    Flow:
      1. Generate a unique call_id and register a warmup Event.
      2. Kick off _prewarm_gemini() as a background task (no await — runs in parallel).
      3. Ask Plivo to place the call (also ~1-2 s, overlaps with step 2).
      4. Return immediately; /answer will wait for the warmup event before
         handing the stream URL to Plivo, so the bot greets with zero cold-start.
    """
    data = await request.json()
    if not data.get("phone_number"):
        raise HTTPException(400, "Missing phone_number")

    phone_number = str(data["phone_number"])
    body_data = data.get("body", {}) or {}
    if not isinstance(body_data, dict):
        body_data = {}
    # So Pipecat /ws receives callee phone inside runner_args.body (scripts use LeadContext).
    body_data = {**body_data, "phone_number": phone_number}
    call_id = str(uuid.uuid4())

    # Register the warmup event BEFORE starting the background task.
    event = asyncio.Event()
    _warmup_ready[call_id] = event

    # Fire pre-warm in the background — overlaps with the Plivo dial request.
    asyncio.create_task(_prewarm_gemini(call_id))

    host = request.headers.get("host", "localhost")
    protocol = "https" if not host.startswith(("localhost", "127.0.0.1")) else "http"
    answer_url = f"{protocol}://{host}/answer?call_id={call_id}"
    if body_data:
        encoded = urllib.parse.quote(json.dumps(body_data))
        answer_url += f"&body_data={encoded}"
    hangup_url = build_hangup_url(call_id, host=host)

    try:
        result = await make_plivo_call(
            session=request.app.state.session,
            to_number=phone_number,
            from_number=os.getenv("PLIVO_PHONE_NUMBER", ""),
            answer_url=answer_url,
            hangup_url=hangup_url,
        )
        call_uuid = result.get("request_uuid", "unknown")
    except Exception as e:
        # Clean up the warmup event so we don't leak memory.
        _warmup_ready.pop(call_id, None)
        raise HTTPException(500, str(e))

    logger.info(f"[start] call_id={call_id}  plivo_uuid={call_uuid}  phone={phone_number}")
    return JSONResponse({
        "call_uuid": call_uuid,
        "call_id": call_id,
        "status": "call_initiated",
        "phone_number": phone_number,
        "route": BOT_ROUTE,
    })


@app.api_route("/plivo-hangup", methods=["GET", "POST"])
async def plivo_hangup(request: Request):
    return await handle_plivo_hangup(request)


@app.api_route("/answer", methods=["GET", "POST"])
async def answer_xml(
    request: Request,
    call_id: str = Query(None),
    CallUUID: str = Query(None),
    body_data: str = Query(None),
) -> HTMLResponse:
    """
    Returns XML that tells Plivo to stream audio to our WebSocket.

    If call_id is present we wait (up to 3 s) for the Gemini pre-warm to
    finish before responding. Plivo calls /answer only after the callee
    picks up, and the prewarm itself usually completes in <2 s — so a
    tight cap here just prevents long stalls if Google is slow without
    eating into the typical happy path. A missed prewarm only costs the
    bot's own Gemini WS cold-start (~1–2 s), which is now overlapped
    with the rest of pipeline setup by the on_client_connected handler.
    """
    if call_id and call_id in _warmup_ready:
        event = _warmup_ready[call_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=3.0)
            logger.info(f"[answer:{call_id}] Gemini warm — sending stream XML")
        except asyncio.TimeoutError:
            logger.warning(f"[answer:{call_id}] Pre-warm timeout — proceeding anyway")
        finally:
            # Clean up; the session is single-use.
            _warmup_ready.pop(call_id, None)

    if call_id and CallUUID:
        pool = getattr(request.app.state, "pool", None)
        if pool is not None:
            asyncio.create_task(
                pg_db.link_call_log_plivo_sid(pool, call_id, CallUUID)
            )

    host = request.headers.get("host", "localhost")
    ws_url = f"wss://{host}/ws"

    # Pass body_data + call_id through to the WebSocket endpoint.
    params: list[str] = []
    if call_id:
        params.append(f"call_id={urllib.parse.quote(call_id)}")
    if body_data:
        try:
            parsed = json.loads(body_data)
            encoded = base64.b64encode(json.dumps(parsed).encode()).decode()
            params.append(f"body={urllib.parse.quote(encoded)}")
        except Exception:
            pass

    if params:
        ws_url += "?" + "&amp;".join(params)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true" contentType="audio/x-mulaw;rate=8000">
        {ws_url}
    </Stream>
</Response>"""

    return HTMLResponse(content=xml, media_type="application/xml")


def _resolve_bot(body_data: dict):
    """Phase 2: per-call route from _pg; Phase 0: module-level _bot."""
    pg = body_data.get("_pg") if isinstance(body_data.get("_pg"), dict) else None
    if pg and pg.get("route"):
        route = pg["route"]
        if route == "cascaded":
            from bot_cascade import bot as dynamic_bot

            return dynamic_bot
        from bot_sts import bot as dynamic_bot

        return dynamic_bot
    return _bot


@app.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    body: str = Query(None),
    call_id: str = Query(None),
):
    await websocket.accept()

    body_data: dict = {}
    if body:
        try:
            body_data = json.loads(base64.b64decode(urllib.parse.unquote(body)).decode())
        except Exception:
            pass
    if not isinstance(body_data, dict):
        body_data = {}
    # Correlate with POST /start response `call_id` (UUID). Not set for ad-hoc WS tests.
    if call_id:
        body_data["_session_call_id"] = call_id
        pg = body_data.get("_pg")
        if isinstance(pg, dict):
            from call_transcript import register_pg_context

            register_pg_context(call_id, pg)

    runner_args = WebSocketRunnerArguments(
        websocket=websocket,
        body=body_data,
    )

    bot_fn = _resolve_bot(body_data)
    try:
        await bot_fn(runner_args)
    except Exception as e:
        import traceback
        logger.error(f"Bot error: {e}\n{traceback.format_exc()}")
        await websocket.close()


@app.get("/health")
async def health():
    return {"status": "ok", "route": BOT_ROUTE}


def _register_api_routes() -> None:
    from api.routes import calls, campaigns, credits, internal, internal_script_configs, leads

    app.include_router(internal.router)
    app.include_router(internal_script_configs.router)
    app.include_router(campaigns.router)
    app.include_router(leads.router)
    app.include_router(calls.router)
    app.include_router(credits.router)


_register_api_routes()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)