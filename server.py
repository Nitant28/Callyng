import asyncio
import base64
import importlib
import json
import os
import re
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)

from logging_setup import configure_logging  # noqa: E402

configure_logging()

import aiohttp  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from loguru import logger  # noqa: E402
from xml.sax.saxutils import escape as xml_escape  # noqa: E402
from slowapi import Limiter, _rate_limit_exceeded_handler  # noqa: E402
from slowapi.util import get_remote_address  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402

from background_tasks import bind_background_tasks, drain_background_tasks, spawn_background_task  # noqa: E402
from call_log_db import init_db  # noqa: E402
from db import postgres as pg_db  # noqa: E402
from db import redis_client as redis_db  # noqa: E402
from db.warmup_state import (  # noqa: E402
    clear_warmup,
    set_warmup_pending,
    set_warmup_ready,
    wait_for_warmup,
)
from telnyx_hangup import handle_telnyx_webhook, handle_plivo_hangup  # noqa: E402
from recording import handle_telnyx_recording, handle_plivo_recording, start_telnyx_recording, start_plivo_recording  # noqa: E402
from telephony import (  # noqa: E402
    build_hangup_url,
    build_texml_stream_xml,
    make_telnyx_call,
    public_telephony_base_url,
)

from api.script_config_validation import normalize_route  # noqa: E402

# ── Select which bot to run ────────────────────────────────────────────────────
BOT_ROUTE = normalize_route(os.getenv("BOT_ROUTE", "sts"))

from pipecat.runner.types import WebSocketRunnerArguments  # noqa: E402

if BOT_ROUTE == "sts":
    from bot_sts import bot as _bot  # noqa: E402
else:
    from bot_cascade import bot as _bot  # noqa: E402


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


def _gemini_prewarm_enabled() -> bool:
    """Opt-in Live session pre-warm. Default off — halves Gemini RPM/sessions per call."""
    raw = (os.getenv("GEMINI_PREWARM") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


async def _prewarm_gemini(call_id: str) -> None:
    """
    Optionally open a real Gemini Live session to absorb cold-start, then
    signal /answer via Redis warmup state.
    """
    if not _gemini_prewarm_enabled():
        logger.debug(f"[prewarm:{call_id}] skipped (GEMINI_PREWARM disabled)")
        await set_warmup_ready(call_id)
        return

    if BOT_ROUTE != "sts":
        logger.debug(f"[prewarm:{call_id}] skipped (BOT_ROUTE={BOT_ROUTE!r})")
        await set_warmup_ready(call_id)
        return

    from google import genai

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning(f"[prewarm:{call_id}] GOOGLE_API_KEY missing; skipping prewarm")
        await set_warmup_ready(call_id)
        return

    try:
        model, config, Content, Part = _prewarm_live_connect_config()
        logger.info(
            f"[prewarm:{call_id}] Connecting to Gemini Live model={model} …"
        )
        client = genai.Client(api_key=api_key)

        async with client.aio.live.connect(
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
        await set_warmup_ready(call_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if BOT_ROUTE != "sts":
        logger.info("[startup] Pre-importing heavy pipecat audio modules …")
        try:
            from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: F401
            logger.info("[startup] Pre-import done — first call will have no import lag")
        except Exception as exc:
            logger.warning(f"[startup] Pre-import warning ({exc}); continuing anyway")
    else:
        logger.info("[startup] Skipping Silero pre-import (BOT_ROUTE=sts)")

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

    try:
        await redis_db.init_redis()
    except Exception as exc:
        logger.error(
            "[startup] Redis init failed ({}). REDIS_URL is required for rate limiting "
            "and call state; refusing to start.",
            exc,
        )
        raise

    app.state.background_tasks: set[asyncio.Task] = set()
    bind_background_tasks(app.state.background_tasks)
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
            
        try:
            running_camps = await pg_db.get_all_running_campaigns(pool)
            if running_camps:
                from dialer.concurrent_dialer import start_dialer
                host = (os.getenv("DIALER_CALLBACK_HOST") or os.getenv("NGROK_URL") or "localhost:7860").strip()
                logger.info(f"[startup] Found {len(running_camps)} running campaigns. Auto-resuming...")
                for camp in running_camps:
                    try:
                        await start_dialer(app, camp["id"], camp["client_id"], host=host)
                    except Exception as e:
                        logger.warning(f"[startup] Failed to auto-resume campaign {camp['id']}: {e}")
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
    from dialer.concurrent_dialer import shutdown_all_dialers

    await shutdown_all_dialers(app)
    await drain_background_tasks()
    await app.state.session.close()
    import sys
    is_testing = "pytest" in sys.modules
    if not is_testing:
        await pg_db.close_pool()
        await redis_db.close_redis()


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=redis_db.redis_url(),
    in_memory_fallback_enabled=False,
)

app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://admin.aakashvani.ai", "https://app.aakashvani.ai", "http://localhost:3000", "http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.post("/start")
@limiter.exempt
async def start_call(request: Request) -> JSONResponse:
    """
    Trigger an outbound call with Telnyx Telephony & Gemini pre-warming.

    Body: { "phone_number": "+91XXXXXXXXXX", "body": { "lead_name": "Rahul" } }
    """
    data = await request.json()
    if not data.get("phone_number"):
        raise HTTPException(400, "Missing phone_number")

    phone_number = str(data["phone_number"])
    body_data = data.get("body", {}) or {}
    if not isinstance(body_data, dict):
        body_data = {}
    body_data = {**body_data, "phone_number": phone_number}
    call_id = str(uuid.uuid4())

    await set_warmup_pending(call_id)
    spawn_background_task(_prewarm_gemini(call_id), f"prewarm_gemini:{call_id}")

    host = request.headers.get("host", "localhost")
    base = public_telephony_base_url(host)
    answer_url = f"{base}/answer?call_id={call_id}"
    if body_data:
        encoded = urllib.parse.quote(json.dumps(body_data))
        answer_url += f"&body_data={encoded}"
    webhook_url = build_hangup_url(call_id, host=host)
    if body_data:
        encoded = urllib.parse.quote(json.dumps(body_data))
        webhook_url += f"&body_data={encoded}"

    try:
        result = await make_telnyx_call(
            session=request.app.state.session,
            to_number=phone_number,
            from_number=os.getenv("TELNYX_PHONE_NUMBER", ""),
            answer_url=answer_url,
            hangup_url=webhook_url,
            webhook_url=webhook_url,
            client_state=json.dumps(body_data),
        )
        call_uuid = result.get("call_control_id") or result.get("request_uuid") or "unknown"
    except Exception as e:
        await clear_warmup(call_id)
        raise HTTPException(500, str(e))

    logger.info(f"[start] call_id={call_id}  telnyx_control_id={call_uuid}  phone={phone_number}")
    return JSONResponse({
        "call_uuid": call_uuid,
        "call_id": call_id,
        "status": "call_initiated",
        "phone_number": phone_number,
        "route": BOT_ROUTE,
        "telephony_provider": "telnyx",
    })


# ── Telnyx Webhook Routes ────────────────────────────────────────────────────

@app.post("/webhooks/telnyx")
@app.api_route("/telnyx-webhook", methods=["GET", "POST"])
@limiter.exempt
async def telnyx_webhook(request: Request):
    return await handle_telnyx_webhook(request)


@app.api_route("/plivo-hangup", methods=["GET", "POST"])
@limiter.exempt
async def plivo_hangup(request: Request):
    return await handle_plivo_hangup(request)


@app.api_route("/plivo-transfer-xml", methods=["GET", "POST"])
@limiter.exempt
async def plivo_transfer_xml(
    request: Request,
    session_call_id: str = Query(""),
):
    from call_transfer import load_transfer_destination

    sid = (session_call_id or "").strip()
    if not sid:
        sid = str(request.query_params.get("session_call_id") or "").strip()
    number = await load_transfer_destination(sid)
    logger.info(
        "transfer-xml method={} session={} dest={}",
        request.method,
        sid or "?",
        number or "MISSING",
    )
    if not number:
        raise HTTPException(404, "transfer destination not found")
    caller_id = xml_escape((os.getenv("TELNYX_PHONE_NUMBER") or "").strip())
    dest = xml_escape(number)
    host = request.headers.get("host", "")
    action = ""
    if sid:
        action_url = (
            f"{public_telephony_base_url(host)}"
            f"/telnyx-webhook?session_call_id={urllib.parse.quote(sid)}"
        )
        action = f' action="{xml_escape(action_url)}" method="POST"'
    caller_attr = f' callerId="{caller_id}"' if caller_id else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Speak>Connecting you to a human agent now.</Speak>"
        f"<Dial timeout=\"45\" redirect=\"false\"{caller_attr}{action}>"
        f"<Number>{dest}</Number></Dial>"
        "</Response>"
    )
    return HTMLResponse(content=xml, media_type="application/xml")


@app.api_route("/plivo-dial-status", methods=["GET", "POST"])
@limiter.exempt
async def plivo_dial_status(request: Request, session_call_id: str = Query("")):
    form: dict = {}
    try:
        form = dict(await request.form())
    except Exception:
        pass
    logger.info(
        "dial-status session={} q={} form={}",
        session_call_id or "?",
        dict(request.query_params),
        form,
    )
    return HTMLResponse(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@app.api_route("/telnyx-recording", methods=["GET", "POST"])
@app.api_route("/plivo-recording", methods=["GET", "POST"])
@limiter.exempt
async def telnyx_recording(request: Request):
    return await handle_telnyx_recording(request)


@app.api_route("/answer", methods=["GET", "POST"])
@limiter.exempt
async def answer_xml(
    request: Request,
    call_id: str = Query(None),
    CallUUID: str = Query(None),
    body_data: str = Query(None),
) -> Any:
    """
    Returns TeXML / XML that tells Telnyx to stream audio to our WebSocket.
    If Telnyx sends a webhook event instead, delegate to handle_telnyx_webhook.
    """
    content_type = request.headers.get("content-type", "").lower()
    if "json" in content_type:
        return await handle_telnyx_webhook(request)

    if call_id:
        ready = await wait_for_warmup(call_id, timeout_s=3.0)
        if ready:
            logger.info(f"[answer:{call_id}] Gemini warm — sending stream XML")
        else:
            logger.warning(f"[answer:{call_id}] Pre-warm timeout — proceeding anyway")

    call_control_id = CallUUID or str(request.query_params.get("call_control_id") or "")
    if call_id and call_control_id:
        pool = getattr(request.app.state, "pool", None)
        if pool is not None:
            spawn_background_task(
                pg_db.link_call_log_telnyx_sid(pool, call_id, call_control_id),
                name=f"link_sid_{call_id}"
            )
            session = getattr(request.app.state, "session", None)
            if session is not None:
                host = request.headers.get("host", "localhost")
                spawn_background_task(
                    start_telnyx_recording(session, call_control_id, call_id, host=host),
                    name=f"start_rec_{call_id}"
                )

    host = request.headers.get("host", "localhost")
    ws_base = public_telephony_base_url(host).replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_base}/ws"

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

    xml = build_texml_stream_xml(ws_url)
    return HTMLResponse(content=xml, media_type="application/xml")


def _resolve_bot(body_data: dict):
    """Resolve bot module per call."""
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
            body_data = json.loads(base64.b64decode(urllib.parse.unquote(body)).decode("utf-8"))
        except Exception:
            try:
                body_data = json.loads(urllib.parse.unquote(body))
            except Exception:
                pass
    if not isinstance(body_data, dict):
        body_data = {}
    if call_id:
        body_data["_session_call_id"] = call_id
        from script_prefetch import pop_prefetched_config

        prefetch = await pop_prefetched_config(call_id)
        if prefetch is not None:
            body_data["_prefetched_config"] = prefetch
        pg = body_data.get("_pg")
        if isinstance(pg, dict):
            from call_transcript import register_pg_context

            await register_pg_context(call_id, pg)

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
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        if call_id and app.state.pool is not None:
            try:
                in_progress = await pg_db.call_log_in_progress(app.state.pool, call_id)
                if in_progress:
                    logger.warning(f"Cleaning up stuck in_progress call {call_id} after WS closed")
                    await pg_db.mark_call_log_not_in_progress(app.state.pool, call_id)
                    from post_call_processor import recover_abandoned_session

                    await recover_abandoned_session(app.state.pool, call_id)
            except Exception as e:
                logger.error(f"Failed to cleanup stuck call log: {e}")


@app.get("/health")
@limiter.exempt
async def health():
    return {
        "status": "ok",
        "route": BOT_ROUTE,
        "telephony_provider": "telnyx",
    }


def _register_api_routes() -> None:
    from api.routes import (
        calls,
        campaigns,
        client_leads,
        credits,
        dashboard,
        events,
        internal,
        internal_messages,
        internal_n8n,
        internal_leads,
        internal_followups,
        internal_script_configs,
        leads,
        messages,
        whatsapp,
    )

    app.include_router(events.router)
    app.include_router(internal.router)
    app.include_router(internal_script_configs.router)
    app.include_router(internal_messages.router)
    app.include_router(internal_n8n.router)
    app.include_router(internal_followups.router)
    app.include_router(internal_leads.router)
    app.include_router(campaigns.router)
    app.include_router(leads.router)
    app.include_router(client_leads.router)
    app.include_router(calls.router)
    app.include_router(credits.router)
    app.include_router(whatsapp.router)
    app.include_router(dashboard.router)
    app.include_router(messages.router)


_register_api_routes()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860, access_log=False)
