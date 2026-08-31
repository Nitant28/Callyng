# Cascade Route — Provider Agnosticism & Malleability (Implementation Plan v3)

> **Status:** Phases 1a, 1b, 2, and 2b **completed** 2026-08-23. Phase 3 (BYOK / telephony adapters) pending. Originally re-verified against Pipecat 1.5.0 on 2026-08-19.
> **Scope:** `/start` → `/answer` → `/ws` → `bot_cascade.py` → pipeline teardown, plus `script_runtime.py`, `script_prefetch.py`, `call_metrics.py`, `call_limits.py`, `call_transcript.py`, `pricing_sts.py`, `billing.py`, `telephony.py`, `plivo_hangup.py`, `post_call_extract.py`, `post_call_processor.py`, DB schema + Alembic, admin API/UI, and tests.

Every claim below was checked against source or against the installed package. Where v2 of this document was wrong, the correction is called out explicitly.

---

## 0. Locked decisions

| # | Decision | Consequence |
|---|---|---|
| D1 | **Generic factory core with per-provider override hooks.** `providers/` is three files: `catalog.py`, `keys.py`, `factory.py`. | Pipecat 1.5 settings are uniform (§2.1), so per-vendor builder files are unnecessary. |
| D2 | **Cascade validation is route-gated.** Provider/model/settings are validated only when `route == "cascaded"`. Unknown settings keys are hard-rejected. | STS rows keep their inert cascade defaults; PATCH does not start failing on existing rows. |
| D3 | **TTS voice is optional.** Blank voice falls back to a per-provider env var. | No existing cascade row breaks. `cascade_tts_voice` stops being required. |
| D4 | **Cold transfer bills only up to the transfer.** Pipeline duration is the billed duration; outcome is `Transferred`. | Post-transfer human talk time is Plivo cost, not client credits. Callback scheduling must be suppressed. |
| D5 | **`eleven_v3` ships in the catalog** (without a `speed` field). | Needs one live smoke call before release; see the pre-merge checklist in §4.2. |
| D6 | **Phase 1 ships as two PRs.** 1a = backend (works with today's UI), 1b = catalog-driven Models tab. | Smaller review surface; 1a is independently deployable. |

---

## 1. Executive summary

The cascade route has strong structural bones. `Pipeline` is provider-agnostic, and metrics, transcript, call limits, and credit billing are all generic. Two things are still hardcoded: **service instantiation in `bot_cascade.py`** (Sarvam STT + Groq LLM + Cartesia TTS) and **telephony** (Plivo-only).

Postgres, the admin API, and Redis prefetch already store and transport provider preferences. The last mile is missing: `CascadeRuntime` drops the provider strings, `bot_cascade.py` ignores them, validation never checks them, and the Models tab does not expose four of the six cascade columns.

**The single most important correction in this revision:** v2 asserted that Pipecat constructors are non-uniform (`voice` vs `voice_id`, differing settings shapes) and therefore mandated hand-written per-vendor builders. **That is false for Pipecat 1.5.0.** All service settings derive from one base class with a shared field vocabulary and a `from_mapping()` constructor. The factory is roughly 80 lines, not three files of branches. Details and evidence in §2.1.

Three hazards v2 missed, each of which would have broken a deploy:

1. **`db/schema/*.sql` is executed by Alembic**, not a decorative mirror (§2.2).
2. **PATCH validates the entire merged row**, so new strict rules apply retroactively to every existing config (§2.4).
3. **The `sonic-3`-as-voice bug lives at seven sites**, not one (§3, F20).

Ship order: **1a** backend last mile → **1b** Models tab → **2** cascade COGS → **2b** transfer + live tools → **3** BYOK and telephony adapters.

---

## 2. Verified platform facts

This section is the factual basis for the plan. Do not redesign against assumptions; these were measured.

### 2.1 Pipecat 1.5.0 has a uniform settings API

Verified by introspecting the installed package (`pipecat.services.settings`).

**Every** service settings class derives from `ServiceSettings` and inherits `model: str | None` plus `extra: dict[str, Any]`. The type-level subclasses are `STTSettings`, `LLMSettings`, and `TTSSettings`.

| Role | Shared fields | Provider-specific additions |
|---|---|---|
| STT | `model`, `extra`, `language` | Deepgram: `smart_format`, `punctuate`, `endpointing`, `interim_results`, `utterance_end_ms`, `numerals`, `profanity_filter`, `diarize`, … Sarvam: `prompt`, `vad_signals`, `high_vad_sensitivity`, VAD thresholds |
| LLM | `model`, `extra`, `system_instruction`, `temperature`, `max_tokens`, `top_p`, `top_k`, `frequency_penalty`, `presence_penalty`, `seed` | Groq/OpenAI: `max_completion_tokens`. Google: `thinking` |
| TTS | `model`, `extra`, `voice`, `language` | Cartesia: `generation_config`, `pronunciation_dict_id`. ElevenLabs: `stability`, `similarity_boost`, `style`, `use_speaker_boost`, `speed`, `apply_text_normalization` |

Consequences that change the design:

- **ElevenLabs settings use `voice`, not `voice_id`.** So do Cartesia's. `voice_id` exists only as an *alias* resolved by `from_mapping()`. The v2 factory sample used `voice_id=` as a keyword and was wrong.
- **Passing `voice_id=` or `model=` as constructor kwargs is deprecated.** Both emit `DeprecationWarning` telling you to use `settings=Service.Settings(...)`. Today's `bot_cascade.py` already uses the `settings=` form for all three services, so we must not regress to constructor kwargs.
- **`Settings.from_mapping(dict)` exists and is the intended entry point.** It resolves aliases, assigns known keys to fields, and dumps everything unrecognized into `extra` — **silently**. That silence is exactly why API-layer validation must reject unknown keys (§4.4); the library will not do it for us.
- **Settings objects are sparse ("delta mode").** Unset fields hold a `NOT_GIVEN` sentinel and the service fills its own defaults. We only need to send keys the operator actually set.
- `api_key` is a constructor kwarg on every service (OpenAI receives it through `BaseOpenAILLMService`).
- `sample_rate` is a constructor kwarg, **not** a settings field.

Both of these construct cleanly offline, with no network and no deprecation warnings:

```python
CartesiaTTSService(
    api_key=key,
    settings=CartesiaTTSSettings.from_mapping({"voice": vid, "model": "sonic-3", "language": "hi"}),
    sample_rate=8000,
)
ElevenLabsTTSService(
    api_key=key,
    settings=ElevenLabsTTSSettings.from_mapping({"voice": vid, "model": "eleven_v3", "stability": 0.4}),
    sample_rate=8000,
)
```

**Genuine outliers** — the only places per-provider code is required:

| Outlier | Handling |
|---|---|
| Cartesia `generation_config` is a nested pydantic model (`volume` 0.5–2.0, `speed` 0.6–1.5, `emotion`; sonic-3/3.5 only) | Catalog uses dotted keys (`generation_config.speed`); the factory reassembles them into `GenerationConfig(...)` |
| Sarvam `mode` (`transcribe`/`translate`/`verbatim`/`translit`/`codemix`) is a **constructor** kwarg with no settings field | Catalog field carries `ctor=True`; the factory routes it to the constructor instead of the settings payload |
| `api_key` env name differs per provider | `catalog.api_key_env` |
| TTS output sample rate | Factory always passes `sample_rate=8000` for TTS |

**8 kHz is safe for ElevenLabs.** `output_format_from_sample_rate(8000)` returns `"pcm_8000"`, so no resampling shim is needed for the Plivo transport contract.

### 2.2 Alembic executes the SQL files

`alembic/versions/006_script_configs.py` and `011_bot_fixed_start_credits.py` both do:

```python
sql = Path("db/schema/006_script_configs.sql").read_text(encoding="utf-8")
for stmt in re.split(r';\s*$', sql, flags=re.MULTILINE):
    if stmt.strip():
        op.get_bind().exec_driver_sql(stmt.strip())
```

Three hard constraints follow:

1. A DDL migration **must** ship both files — the `.py` loader and the `.sql` body. `db/schema/` is not a documentation mirror.
2. `Path(...)` is **relative**, so `alembic upgrade` must run from the repo root.
3. The splitter is a naive regex on line-terminating semicolons. **No `DO $$ … $$` blocks, no function or trigger bodies.** Plain `ALTER` / `UPDATE` / `CREATE INDEX` statements only.

`db/schema/` holds only `001`–`006` and `011` because `007`–`010` are pure-Python data migrations. The convention is therefore: **DDL → `.sql` + loader; data-only → inline Python.** Migration `012` is DDL plus a small repair `UPDATE`, so it follows the `006`/`011` pattern. Current head is `011_bot_fixed_start_credits`.

### 2.3 Column plumbing is hardcoded in four places

In `db/postgres.py`, adding a `script_configs` column means editing all of these:

| Location | Lines | Mechanism |
|---|---|---|
| `create_script_config` | 725–817 | Hardcoded INSERT column list (30 columns) + positional `$N` placeholders + one explicit `data.get(...)` per field |
| `_SCRIPT_CONFIG_PATCHABLE` | 820–851 | `frozenset` gating PATCH |
| `_SCRIPT_CONFIG_JSONB` | 853–866 | JSONB cast list |
| `rollback_script_config` | 1033–1052 | Reuses `_SCRIPT_CONFIG_PATCHABLE` — **automatic** once that set is updated |

Nothing is derived from dict keys. Plus `_SNAPSHOT_COLUMNS` in `api/script_config_validation.py` (28–58) and the two Pydantic models in `api/routes/internal_script_configs.py` (29–95).

### 2.4 PATCH validates the whole merged row

`patch_script_config` (`api/routes/internal_script_configs.py` 185–211):

```python
merged = _merged_for_validation(current, patch)
validate_script_config_payload(merged, partial=False)
```

So any new rule applies to **every existing row on its next save**, not just to the fields being changed. Combined with the fact that STS rows carry cascade defaults (written by `default_template()` and `export_sts_module()`), unconditional cascade validation would make currently-savable STS configs unsavable. This is why D2 gates on `route == "cascaded"`.

### 2.5 Admin UI

`frontend/src/admin/pages/AdminScriptConfigs.jsx`:

| Thing | Location |
|---|---|
| `activeTab` state | 265 |
| Tab bar (`general`, `prompts`, `models`, `post-call`, `advanced`) | 794–800 |
| Models tab | 847–914 |
| Gemini fields, gated on `route === 'sts'` | 849–870 |
| Cascade fields (`cascade_stt_provider`, `cascade_llm_model` — free text, both) | 871–884 |
| VAD sliders — **not** route-gated, shown for cascade too | 886–912 |
| `cascade_live_tools` raw JSON textarea (Advanced) | 952–953 |
| `handleEditorChange(key, value)` | 397–399 |
| `saveConfig` — `payload = { ...editingConfig }`, parses 11 JSON string fields, strips `id`/`client_id`/`version`/`created_at`/`updated_at` | 401–470 |

API access is the default axios export from `frontend/src/shared/api/admin.js`, which attaches an `X-Admin-Key` interceptor. A new endpoint is reached with `adminApi.get('/internal/cascade-providers')`.

Because `saveConfig` spreads the whole editing object, **stale settings keys will be transmitted** unless the UI prunes them on provider/model change. Server-side rejection is the enforcement point; UI pruning is the ergonomics.

### 2.6 Cost path

- `call_transcript.attach_pipeline_finalize` (470–483) computes `cost_inr = compute_sts_cost_inr(route, ...)` at 529–542, with `up`, `uc`, `ut`, `tts_c`, `duration_ms`, `duration_seconds`, and `usage_summary` all in scope.
- That value reaches **SQLite only**, via `insert_call_log(..., cost_inr=...)` at 544–560, and the n8n payload at 689/725.
- On the Postgres side, pipeline teardown only calls `mark_call_log_not_in_progress` (569–578).
- `db/postgres.finalize_call_log` (3599–3671) writes `duration_seconds`, `billed_minutes`, `credits_charged`, `outcome`, `qualified`, `extraction_json`, the four usage columns, extraction model/error, `call_data`, and optionally `transcript`. It **never touches `cost_usd`**, and it receives neither `route` nor provider names — only a `usage: dict`.
- Callers: `call_transcript.py:157` (test-call path) and `post_call_processor._finalize_call_log_and_settle_budget:238`.

The `usage` dict is threaded end-to-end from the pipeline to both call sites, which makes it the cheapest cost carrier (§6).

### 2.7 Test harness

`tests/conftest.py` has a session-scoped `autouse` fixture that attempts to init the Postgres pool and Redis but **wraps both in `try/except`**, setting `app.state.pool = None` on failure. Pure unit tests therefore run without any live infrastructure. `mock_is_call_allowed` is also autouse.

`tests/test_post_call_providers.py` is the dispatcher-test pattern to copy: an autouse fixture clearing provider env vars, `monkeypatch.setenv` per case, and `patch("post_call_extract._post_json", new=AsyncMock(...))` capturing the outbound request. It never hits the network.

### 2.8 Environment

Present in `env.example`: `GOOGLE_API_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY`, `CARTESIA_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_VOICE_ID`, `OPENAI_API_KEY`, `USD_INR=84.0`, commented `GEMINI_LIVE_*_USD_PER_1M`.

Missing: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `SONIOX_API_KEY`.

`pyproject.toml` extras: `cartesia, deepgram, elevenlabs, google, groq, openai, runner, sarvam, silero, websocket`. **No `soniox`**, no `cryptography`.

### 2.9 Outcome vocabulary

`call_outcomes.py` splits outcomes into `TERMINAL` / `CALLBACK` / `RETRY` / `FAILURE`, plus a `SYSTEM_OUTCOMES` set for outcomes produced by dialer and telephony logic rather than LLM intent extraction. System outcomes are deliberately excluded from a script config's `outcome_terminal`/`retry`/`callback` lists, so `validate_outcome_mapping` (which requires an exact match against the `intent_status` enum) is unaffected by them.

That is the correct home for `Transferred` (D4) — see §7.

---

## 3. Audit findings

Ratings unchanged unless noted. **Bold** entries changed materially since v2.

| ID | Finding | Severity | Status |
|---|---|---|---|
| F1 | Provider strings stored but never consumed | Critical | **Shipped Phase 1a** |
| F2 | Hardcoded service imports in `bot_cascade.py` | Critical | **Shipped Phase 1a** |
| **F3** | Provider-specific settings leakage | High | **Rationale corrected — see below** |
| F4 | Hardcoded 8 kHz sample rate | Medium | Confirmed; keep as transport contract |
| F5 | API key resolution is implicit | High | **Shipped Phase 1a** (env; BYOK still Phase 3) |
| F6 | No provider cost for cascade | High | **Shipped Phase 2** |
| F7 | No provider validation at the API layer | Medium | **Shipped Phase 1a** |
| F8 | Default `push_lead_data` schema leaks domain logic | Low | Confirmed |
| F9 | Extras installed but unused | Info | Confirmed |
| F10 | No failover | Medium | Deferred to Phase 4 |
| F11 | `cascade_scripts/` has one script | Info | Confirmed |
| F12 | Tests cover runtime, not the bot | High | Confirmed |
| F13 | Telephony hardcoded to Plivo | High | Confirmed |
| F14 | No call transfer | High | **Shipped Phase 2b** (cold transfer; warm/SIP still out of scope) |
| F15 | Live tools are a toggle + JSON, not a webhook framework | High | **Shipped Phase 2b** as toggle + JSON (webhook runner still out of scope) |
| F16 | No BYOK | High | Phase 3 |
| F17 | Missing provider wiring | Medium | **Shipped Phase 1a** |
| F18 | `telephony/` directory empty and name-clashing | Info | Confirmed |
| F19 | Admin Models tab incomplete | High | **Shipped Phase 1b** |
| **F20** | TTS voice vs model conflation | High | **Seven sites, not one** |
| F21 | No cascade language/temperature columns | Medium | Resolved by settings JSONB |
| F22 | Silero VAD vs script-config VAD | Low | **Shipped Phase 1b** — VAD block STS-only |
| F23 | Hardcoded "Diya" persona in logs | Info | Confirmed (L102, L219) |
| F24 | `push_lead_data` does not persist | Medium | Confirmed |
| F25 | `cost_usd` column is dead | Low | **Shipped Phase 2** (internal COGS; stripped from client APIs) |
| **F26** | PATCH validates the full merged row | High | **New** |
| **F27** | `db/schema/*.sql` is executed by Alembic | High | **New** |

### F1 — Provider strings stored but never consumed

| Layer | Has provider fields? | Reads them? |
|---|---|---|
| `db/schema/006_script_configs.sql` | Yes — all three `cascade_*_provider` | N/A |
| `api/routes/internal_script_configs.py` 45–49 / 82–86 | Yes, create and patch | N/A |
| `script_prefetch.render_script_config` 128–132 | Yes, forwarded to Redis | N/A |
| `CascadeRuntime` (`script_runtime.py` 184–194) | **No** | Drops them |
| `_cascade_from_prefetch` 530–545 | **No** | Ignores them |
| `bot_cascade.py` 108–133 | **No** | Hardcoded classes |
| Admin Models tab | Only `cascade_stt_provider` | See F19 |

DB → API → Redis does work the bot cannot deliver on.

### F3 — Provider-specific settings leakage (rationale corrected)

Still hardcoded today: Sarvam `language="unknown"`, Groq `temperature=0.2`, Cartesia `model="sonic-3"` and `language="hi"`. There is still no carrier for per-provider extras.

**v2's stated reason was wrong.** It claimed a generic factory is impossible because "Pipecat constructors are not uniform (`voice` vs `voice_id`, Gemini Live vs `GoogleLLMService`, sample_rate placement)." Per §2.1, the settings API *is* uniform, `voice_id` is merely an alias for `voice`, and `sample_rate` is consistently a constructor kwarg. The correct reason to keep an allow-list is **product safety, not API shape**: we must not let an operator select a model Pipecat cannot stream at 8 kHz, and we must not silently pass a stale `speed` into `extra`. A curated catalog plus a thin generic builder delivers that with far less code (D1).

### F20 — TTS voice vs model conflation (seven sites)

`cascade_tts_voice TEXT DEFAULT 'sonic-3'`, but `sonic-3` is Cartesia's **model**; voices are UUIDs. There is no `cascade_tts_model` column, so a row can pass the model name as a voice id. Module-path calls fall back to `CARTESIA_VOICE_ID`, which is why local testing still sounds right.

Every site that writes or defaults `'sonic-3'` into the **voice** slot:

1. `db/schema/006_script_configs.sql` — column `DEFAULT 'sonic-3'`
2. `script_prefetch.render_script_config` L133 — `or "sonic-3"`
3. `api/script_config_validation.default_template()` L348
4. `api/routes/internal_script_configs.CreateScriptConfigBody` L50
5. `script_module_export.export_sts_module` L110
6. `script_module_export.export_cascade_module` L147
7. `script_runtime._cascade_from_prefetch` L533 — `os.getenv("CARTESIA_VOICE_ID", "") or "sonic-3"`

All seven change in Phase 1a, plus a data repair in migration `012`.

---

## 4. Phase 1a — backend last mile

Deployable on its own. The existing Models tab keeps working (it edits two free-text fields that remain valid catalog values).

### 4.1 Step 1 — `CascadeRuntime` carries providers, models, and settings

**File:** `script_runtime.py`

```python
@dataclass(frozen=True)
class CascadeRuntime:
    script_id: str
    source: str
    system_prompt: str
    extraction_schema: dict[str, Any]
    stt_provider: str
    stt_model: str
    stt_settings: dict[str, Any]
    llm_provider: str
    llm_model: str
    llm_settings: dict[str, Any]
    tts_provider: str
    tts_model: str
    tts_voice: str                  # "" is valid; factory falls back to the provider's voice env (D3)
    tts_settings: dict[str, Any]
    push_lead_data_schema: FunctionSchema | None
    live_tools: list[Any] = field(default_factory=list)   # raw JSON, consumed in Phase 2b
    module_name: str = ""
```

`_cascade_from_prefetch()` reads `cascade_{stt,llm,tts}_provider`, `cascade_{stt,llm}_model`, the new `cascade_tts_model`, and the three `cascade_*_settings` dicts, defaulting each provider/model through `catalog.default_provider(kind)` / `catalog.default_model(kind, provider)` rather than module-level string constants.

Voice resolution — **delete the `or "sonic-3"` fallback**:

```python
voice = str(prefetch.get("cascade_tts_voice") or "")
if voice == str(prefetch.get("cascade_tts_model") or ""):
    voice = ""      # defensive: a pre-012 row that stored the model name as the voice
```

Leave the env fallback to the factory, which knows the provider's `voice_env`.

`_cascade_from_module()` uses catalog defaults, empty settings dicts, and `tts_voice=""`.

Replace `_DEFAULT_CASCADE_STT_MODEL` / `_DEFAULT_CASCADE_LLM_MODEL` / `_DEFAULT_CASCADE_TTS_VOICE_ENV` with catalog lookups so there is exactly one source of defaults.

### 4.2 Step 2 — `providers/catalog.py`

The **only** place vendor, model, and field options are listed. Factory, API validation, and the admin form all read it. Adding a model is an edit here; adding a *vendor* additionally needs one line in the factory's service map.

```python
# providers/catalog.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal

FieldType = Literal["string", "select", "number", "boolean"]


@dataclass(frozen=True)
class Field:
    key: str                       # Pipecat Settings field name, or "group.name" for nested
    label: str
    type: FieldType
    default: Any = None
    options: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    required: bool = False
    ctor: bool = False             # route to the constructor, not the settings payload


@dataclass(frozen=True)
class ModelSpec:
    label: str
    fields: tuple[Field, ...] = ()

    @property
    def field_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.fields)


@dataclass(frozen=True)
class ProviderSpec:
    label: str
    api_key_env: str
    default_model: str
    models: dict[str, ModelSpec]
    voice_env: str | None = None   # TTS only; fallback when cascade_tts_voice is blank
```

Shape of the three catalogs (abridged — `LLM_CATALOG` follows the same pattern):

```python
_LANG = ("hi", "en", "mr")

STT_CATALOG: dict[str, ProviderSpec] = {
    "sarvam": ProviderSpec(
        label="Sarvam",
        api_key_env="SARVAM_API_KEY",
        default_model="saarika:v2.5",
        models={
            "saarika:v2.5": ModelSpec("Saarika v2.5", (
                Field("language", "Language", "select",
                      options=("unknown", "hi-IN", "mr-IN", "en-IN"), default="unknown"),
            )),
            "saaras:v3": ModelSpec("Saaras v3", (
                Field("language", "Language", "select",
                      options=("unknown", "hi-IN", "mr-IN", "en-IN"), default="unknown"),
                # `mode` is saaras-only AND constructor-only
                Field("mode", "Mode", "select",
                      options=("transcribe", "translate", "verbatim", "translit", "codemix"),
                      default="transcribe", ctor=True),
            )),
        },
    ),
    "deepgram": ProviderSpec(
        label="Deepgram",
        api_key_env="DEEPGRAM_API_KEY",
        default_model="nova-2",
        models={
            "nova-2": ModelSpec("Nova-2", (
                Field("language", "Language", "select", options=_LANG + ("multi",), default="hi"),
                Field("smart_format", "Smart format", "boolean", default=True),
                Field("punctuate", "Punctuate", "boolean", default=True),
                Field("utterance_end_ms", "Utterance end (ms)", "number",
                      min=500, max=5000, step=100, default=1000),
            )),
        },
    ),
}

_EL_FIELDS = (
    Field("voice", "Voice ID", "string"),
    Field("language", "Language", "select", options=_LANG, default="hi"),
    Field("stability", "Stability", "number", min=0, max=1, step=0.05, default=0.5),
    Field("similarity_boost", "Similarity", "number", min=0, max=1, step=0.05, default=0.75),
    Field("use_speaker_boost", "Speaker boost", "boolean", default=True),
)
_EL_SPEED = (Field("speed", "Speed", "number", min=0.7, max=1.2, step=0.05, default=1.0),)

TTS_CATALOG: dict[str, ProviderSpec] = {
    "cartesia": ProviderSpec(
        label="Cartesia",
        api_key_env="CARTESIA_API_KEY",
        voice_env="CARTESIA_VOICE_ID",
        default_model="sonic-3",
        models={
            "sonic-3": ModelSpec("Sonic 3", (
                Field("voice", "Voice ID", "string"),
                Field("language", "Language", "select", options=_LANG, default="hi"),
                Field("generation_config.speed", "Speed", "number",
                      min=0.6, max=1.5, step=0.05, default=1.0),
                Field("generation_config.volume", "Volume", "number",
                      min=0.5, max=2.0, step=0.05, default=1.0),
                Field("generation_config.emotion", "Emotion", "string"),
            )),
        },
    ),
    "elevenlabs": ProviderSpec(
        label="ElevenLabs",
        api_key_env="ELEVENLABS_API_KEY",
        voice_env="ELEVENLABS_VOICE_ID",
        default_model="eleven_turbo_v2_5",
        models={
            "eleven_multilingual_v2": ModelSpec("Multilingual v2", _EL_FIELDS + _EL_SPEED),
            "eleven_turbo_v2_5":      ModelSpec("Turbo v2.5",      _EL_FIELDS + _EL_SPEED),
            "eleven_flash_v2_5":      ModelSpec("Flash v2.5",      _EL_FIELDS + _EL_SPEED),
            "eleven_v3":              ModelSpec("Eleven v3",       _EL_FIELDS),   # no speed (D5)
        },
    ),
}
```

Rules for this file:

- **Curated, never live-fetched in Phase 1.** A missing vendor key must not blank the admin form.
- **List only models the factory can actually construct and stream at 8 kHz.** Not in the catalog ⇒ the UI cannot select it and validation rejects it.
- **`Field.key` must be the real Pipecat settings field name** (or `group.name` for nested), so the factory needs no translation table.
- Voice IDs stay free-text in Phase 1 (voice libraries are account-specific). Model IDs never are.

Helpers in the same module — `default_provider(kind)`, `default_model(kind, provider)`, `get_provider(kind, provider)`, `get_model(kind, provider, model)` (raising `ValueError`, not `KeyError`), and `catalog_as_json()` for the API.

`catalog_as_json()` omits `api_key_env` and adds a computed `key_configured: bool` per provider so the UI can warn about an unconfigured vendor without leaking env names.

> **Pre-merge checklist for this file.** Model IDs age fast; confirm each against the vendor before merge and record the date in a comment at the top of the file:
> - Groq — `GET https://api.groq.com/openai/v1/models`, keep only chat models `GroqLLMService` accepts
> - OpenAI — `GET https://api.openai.com/v1/models`
> - Google — `GET https://generativelanguage.googleapis.com/v1beta/models`, filter on `supportedGenerationMethods`
> - Deepgram — `GET https://api.deepgram.com/v1/models`, keep `streaming: true` only
> - ElevenLabs — `GET https://api.elevenlabs.io/v1/models`, `can_do_text_to_speech` only; **make one live 8 kHz call on `eleven_v3` before shipping it (D5)** and drop it if the realtime websocket path rejects it
> - Cartesia, Sarvam — no list endpoint; transcribe the OpenAPI enum

### 4.3 Step 3 — `providers/keys.py` and `providers/factory.py`

`keys.py` mirrors `post_call_extract._resolve_provider_key`: one function, explicit env names, a clear error when missing. It is `async` and accepts `client_id`/`pool` **from day one** so Phase 3 BYOK is a change to this file alone, not a bot rewrite. Both may be `None` (local WS testing has no pool).

```python
async def resolve_api_key(env_name: str, *, provider: str,
                          client_id=None, pool=None) -> str:
    key = (os.getenv(env_name) or "").strip()
    if not key:
        raise ValueError(f"{provider}: {env_name} is not set")
    return key
```

`factory.py` is the generic core (D1):

```python
TELEPHONY_SAMPLE_RATE = 8000

_SERVICES = {
    ("stt", "sarvam"):     (SarvamSTTService,    SarvamSTTSettings),
    ("stt", "deepgram"):   (DeepgramSTTService,  DeepgramSTTSettings),
    ("llm", "groq"):       (GroqLLMService,      GroqLLMSettings),
    ("llm", "openai"):     (OpenAILLMService,    OpenAILLMSettings),
    ("llm", "google"):     (GoogleLLMService,    GoogleLLMSettings),
    ("tts", "cartesia"):   (CartesiaTTSService,  CartesiaTTSSettings),
    ("tts", "elevenlabs"): (ElevenLabsTTSService, ElevenLabsTTSSettings),
}

_NESTED = {"generation_config": GenerationConfig}


def _split_nested(flat: dict[str, Any]) -> dict[str, Any]:
    """Fold dotted keys into their nested pydantic model."""
    plain, groups = {}, {}
    for key, value in flat.items():
        head, _, tail = key.partition(".")
        if tail:
            groups.setdefault(head, {})[tail] = value
        else:
            plain[key] = value
    for group, values in groups.items():
        plain[group] = _NESTED[group](**values)
    return plain


async def _build(kind, provider, model, settings, *,
                 client_id=None, pool=None, **overrides):
    provider = provider or catalog.default_provider(kind)
    model = model or catalog.default_model(kind, provider)
    spec = catalog.get_provider(kind, provider)          # ValueError if unknown
    mspec = catalog.get_model(kind, provider, model)     # ValueError if unknown

    api_key = await resolve_api_key(spec.api_key_env, provider=provider,
                                    client_id=client_id, pool=pool)

    payload: dict[str, Any] = {"model": model}
    ctor: dict[str, Any] = {"api_key": api_key}
    if kind == "tts":
        ctor["sample_rate"] = TELEPHONY_SAMPLE_RATE

    for f in mspec.fields:                # catalog order; unknown keys never reach here
        if f.key not in settings:
            continue
        (ctor if f.ctor else payload)[f.key] = settings[f.key]

    payload.update(overrides)             # system_instruction, resolved voice
    cls, settings_cls = _SERVICES[(kind, provider)]
    return cls(settings=settings_cls.from_mapping(_split_nested(payload)), **ctor)
```

Three thin public wrappers:

```python
async def create_stt_service(provider, model, settings, *, client_id=None, pool=None): ...

async def create_llm_service(provider, model, settings, *, system_prompt,
                             client_id=None, pool=None):
    return await _build("llm", provider, model, settings,
                        client_id=client_id, pool=pool,
                        system_instruction=system_prompt)

async def create_tts_service(provider, model, settings, *, voice="",
                             client_id=None, pool=None):
    spec = catalog.get_provider("tts", provider or catalog.default_provider("tts"))
    resolved = (voice or settings.get("voice") or
                os.getenv(spec.voice_env or "", "")).strip()          # D3
    if not resolved:
        raise ValueError(f"{spec.label}: no voice id (set one on the script config "
                         f"or export {spec.voice_env})")
    return await _build("tts", provider, model, settings,
                        client_id=client_id, pool=pool, voice=resolved)
```

Iterating `mspec.fields` rather than the caller's dict is what makes stale keys structurally impossible: a leftover `speed` cannot reach `eleven_v3`, because `eleven_v3`'s field list has no `speed` entry. Unknown providers and models raise `ValueError` **before the pipeline starts**.

### 4.4 Step 4 — validation against the catalog

**File:** `api/script_config_validation.py`

Add the three settings blobs to `_JSON_DICT_FIELDS` so they are coerced like the other JSONB dicts, and add all four new columns to `_SNAPSHOT_COLUMNS`.

New `validate_cascade_config(data)`, called from `validate_script_config_payload` after `validate_route`:

```python
if normalize_route(str(data.get("route") or "")) != "cascaded":
    return                                  # D2 — STS rows keep inert cascade defaults
```

Then per role (`stt`, `llm`, `tts`):

1. Blank/absent provider or model is **accepted** and resolved to the catalog default at prefetch time. A non-blank value must exist in the catalog.
2. `cascade_{role}_settings` must be a dict.
3. Every key must be in that model's `field_keys` → otherwise `ValueError` naming the offending keys and the selected model. This is what stops a stale `speed` from surviving a model switch.
4. `number` fields must coerce to float and sit within `[min, max]`.
5. `select` fields must be in `options`; `boolean` fields must be real booleans.
6. `required` fields must be present and non-empty. (Nothing is required in Phase 1 under D3, but the mechanism ships now.)

Error messages name the field, the selected provider/model, and the allowed values — the admin UI surfaces the 422 body verbatim.

### 4.5 Step 5 — `bot_cascade.py` uses the factory

Delete the three vendor imports and replace lines 108–133. **Pipeline order is unchanged.**

```python
client_id = pg.get("client_id")
pool = _optional_pool()          # may be None on local WS runs

stt = await create_stt_service(runtime.stt_provider, runtime.stt_model,
                               runtime.stt_settings, client_id=client_id, pool=pool)
llm = await create_llm_service(runtime.llm_provider, runtime.llm_model,
                               runtime.llm_settings, system_prompt=runtime.system_prompt,
                               client_id=client_id, pool=pool)
tts = await create_tts_service(runtime.tts_provider, runtime.tts_model,
                               runtime.tts_settings, voice=runtime.tts_voice,
                               client_id=client_id, pool=pool)
```

Also in this step (F23): replace `"Starting cascaded bot — Diya"` (L102) and `"Call connected — Diya starting"` (L219) with `runtime.script_id` and the resolved provider/model triple. A one-line startup log of the three `provider/model` pairs is the single most useful diagnostic this whole phase adds — include it.

Construction failure must surface as a clear log line naming the provider, model, and missing env var, then abort the call rather than half-building a pipeline.

### 4.6 Step 6 — migration `012`

Two files, per §2.2.

`db/schema/012_cascade_provider_settings.sql`:

```sql
-- Cascade: explicit TTS model + per-role settings blobs.

ALTER TABLE script_configs
    ADD COLUMN IF NOT EXISTS cascade_tts_model    TEXT  DEFAULT 'sonic-3',
    ADD COLUMN IF NOT EXISTS cascade_stt_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS cascade_llm_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS cascade_tts_settings JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE script_configs
   SET cascade_tts_model = 'sonic-3'
 WHERE cascade_tts_model IS NULL;

-- Repair rows that stored the Cartesia model name in the voice column (F20).
UPDATE script_configs
   SET cascade_tts_voice = NULL
 WHERE cascade_tts_voice = 'sonic-3';

-- Voice is optional from here on (D3); stop defaulting it to a model name.
ALTER TABLE script_configs
    ALTER COLUMN cascade_tts_voice DROP DEFAULT;
```

Plain statements only — no `DO` blocks, per §2.2.

`alembic/versions/012_cascade_provider_settings.py` copies the `011` loader verbatim, with `down_revision = "011_bot_fixed_start_credits"`.

**Identity lives in columns** (`cascade_*_provider`, `cascade_*_model`, `cascade_tts_voice`); **tunables live in the JSONB blobs**. This is why F21 needs no `cascade_stt_language` / `cascade_tts_language` / `cascade_llm_temperature` columns — they are catalog fields inside `cascade_*_settings`. Do not add a column per vendor knob.

### 4.7 Step 7 — plumb the four columns

Mechanical, but every one of these is load-bearing:

| File | Change |
|---|---|
| `db/postgres.py` | INSERT list + `$N` + defaults in `create_script_config`; 4 keys into `_SCRIPT_CONFIG_PATCHABLE`; 3 settings keys into `_SCRIPT_CONFIG_JSONB` |
| `api/routes/internal_script_configs.py` | `cascade_tts_model` + 3 settings fields on both Pydantic models; drop `cascade_tts_voice = "sonic-3"` default to `""` |
| `api/script_config_validation.py` | `_SNAPSHOT_COLUMNS`, `_JSON_DICT_FIELDS`, `default_template()` (voice `""`, model `"sonic-3"`) |
| `script_prefetch.py` | Forward `cascade_tts_model` and the 3 settings dicts; **delete the `or "sonic-3"` voice default** at L133 |
| `script_module_export.py` | Both export functions: `cascade_tts_model`, empty settings dicts, voice `""` |

Also add `ELEVENLABS_API_KEY=` and `ELEVENLABS_VOICE_ID=` to `env.example`. Do **not** add the `soniox` extra or `cryptography` yet.

### 4.8 Step 8 — `GET /internal/cascade-providers`

In `api/routes/internal_script_configs.py`, behind `require_admin`, no DB access:

```python
@router.get("/cascade-providers")
async def get_cascade_providers(_: None = Depends(require_admin)):
    return catalog_as_json()
```

Response shape (consumed by Phase 1b):

```json
{
  "stt": { "sarvam": { "label": "Sarvam", "default_model": "saarika:v2.5",
                       "key_configured": true,
                       "models": { "saarika:v2.5": { "label": "Saarika v2.5",
                                                     "fields": [ ... ] } } } },
  "llm": { ... },
  "tts": { ... }
}
```

### 4.9 Step 9 — tests

All four run without Postgres or Redis (§2.7).

| File | Covers |
|---|---|
| `tests/test_provider_catalog.py` | Every `default_model` exists in its own `models`; every `Field.key` is a real settings field on the mapped Pipecat class (introspect `dataclasses.fields`) or a known nested path; `eleven_v3` has no `speed` while `eleven_turbo_v2_5` does; `catalog_as_json()` never leaks `api_key_env` |
| `tests/test_provider_factory.py` | Each provider builds with a monkeypatched key; unknown provider and unknown model raise `ValueError`; a stale key in the settings dict is dropped rather than reaching `extra`; Cartesia dotted keys become a `GenerationConfig`; Sarvam `mode` reaches the constructor and not the settings; missing env key raises a named error; TTS voice falls back to `voice_env` and raises when both are blank |
| `tests/test_provider_validation.py` | Bad provider, bad model, unknown settings key, out-of-range number, bad select value; **an STS payload with cascade defaults still validates** (D2 regression guard); blank provider is accepted |
| `tests/test_cascade_runtime_providers.py` | Prefetch → `CascadeRuntime` carries providers, models, settings; pre-012 `sonic-3`-as-voice collapses to `""`; module path gets catalog defaults |

Extend `tests/test_script_runtime.py::test_resolve_cascade_runtime_prefetch_hit` to assert the provider fields it currently ignores, and `tests/test_script_prefetch.py` to assert the new keys are forwarded.

The catalog-vs-Pipecat introspection assertion in `test_provider_catalog.py` is the highest-value test here: it turns a Pipecat upgrade that renames a settings field into a failing unit test instead of a 3 a.m. call failure.

No live websocket test in Phase 1.

---

## 5. Phase 1b — catalog-driven Models tab

**File:** `frontend/src/admin/pages/AdminScriptConfigs.jsx`. Fetch the catalog once when the editor opens (`adminApi.get('/internal/cascade-providers')`), cache it in component state, and render only when `editingConfig.route === 'cascaded'`. **No vendor names or model IDs in JSX.**

Three columns (STT / LLM / TTS), each three tiers:

1. **Provider** `<select>` — keys of `catalog[kind]`. Show an inline warning when `key_configured` is false.
2. **Model** `<select>` — only `catalog[kind][provider].models`. Switching TTS to ElevenLabs replaces the list entirely; Cartesia models disappear.
3. **Settings** — render `models[model].fields` by type: `string` → text, `select` → `<select>` from `options`, `number` → number input with `min`/`max`/`step`, `boolean` → checkbox. A field absent from the model's list is simply not rendered.

Field-key mapping:

| Stored column | Control |
|---|---|
| `cascade_stt_provider` / `_model` / `_settings` | STT column |
| `cascade_llm_provider` / `_model` / `_settings` | LLM column |
| `cascade_tts_provider` / `_model` / `_settings` | TTS column |
| `cascade_tts_voice` | The TTS `voice` field, kept in sync with the existing column |

**Cascade reset behaviour** (this is the part that must not be hand-waved, since `saveConfig` spreads `editingConfig` wholesale, §2.5):

- On **provider** change: set model to that provider's `default_model`, then rebuild settings from scratch using the new model's field defaults.
- On **model** change: drop every settings key absent from the new field list, then apply defaults for newly visible keys.

Without this pruning the server returns a 422 on the next save — correct behaviour, but a confusing experience.

Also in this PR: **route-gate the VAD block** (currently lines 886–912, shown unconditionally). Cascade uses `SileroVADAnalyzer()` with library defaults and never reads those columns (F22), so displaying them for a cascade config is actively misleading. Hide the Gemini model/voice/language/temperature block for cascade too.

`future_updates.md` §11 (hide speed on ElevenLabs v3 and similar) is delivered here, not deferred.

---

## 6. Phase 2 — cascade COGS

Independent of Phase 1b; can start once Step 1 lands.

### 6.1 `pricing_cascade.py`

Use only data we already capture:

| Cost | Input | Rate env |
|---|---|---|
| STT | `duration_seconds` | `STT_{PROVIDER}_USD_PER_MIN` |
| LLM | `usage_prompt_tokens`, `usage_completion_tokens` | `LLM_{PROVIDER}_INPUT_USD_PER_1M`, `LLM_{PROVIDER}_OUTPUT_USD_PER_1M` |
| TTS | `usage_tts_characters` | `TTS_{PROVIDER}_USD_PER_1K_CHARS` |

`UsageMetricsAccumulator` captures LLM tokens and TTS characters but **not** STT audio seconds, so STT cost derives from call duration. Do not invent STT usage frames in this phase.

```python
def compute_cascade_cost_usd(
    *, duration_seconds: int,
    usage_prompt_tokens: int, usage_completion_tokens: int, usage_tts_characters: int,
    stt_provider: str, llm_provider: str, tts_provider: str,
) -> float | None:
```

Returns `None` when **no** component rate is configured; otherwise sums the configured components and treats unconfigured ones as zero, logging once at debug which were skipped. This matches `compute_sts_cost_inr`'s "unconfigured means unknown" contract while still producing a useful partial number.

Factor the `USD_INR` read (default 85, `env.example` sets 84.0) into a shared helper. **Leave `pricing_sts.compute_sts_cost_inr`'s signature untouched** so existing behaviour and tests are unaffected.

### 6.2 Wiring

In `call_transcript.attach_pipeline_finalize` (the block at 529–542), dispatch on route. Provider names are not currently in scope there, so add an optional `providers: dict[str, str] | None = None` parameter and pass `{"stt": runtime.stt_provider, "llm": ..., "tts": ...}` from `bot_cascade.py`. When it is `None` (STS, module paths), behaviour is exactly as today.

**Persisting to Postgres (F25).** `finalize_call_log` receives neither route nor providers — only `usage: dict` (§2.6). Rather than change three signatures across two modules, put the computed value into the usage summary before it is serialized:

```python
usage_summary["cost_usd"] = cost_usd      # before json.dumps for usage_metrics_json
```

`usage` is already threaded end-to-end to both `finalize_call_log` call sites, so `finalize_call_log` gains one line — `cost_usd = $N` sourced from `usage.get("cost_usd")` — and the value simultaneously lands in the SQLite `usage_metrics_json` blob. Keep writing SQLite `cost_inr` as today for webhook compatibility.

`post_call_processor.recover_abandoned_session` rebuilds usage from DB columns and will not have a cost; leaving `cost_usd` NULL for recovered sessions is acceptable. Note it in the docstring rather than back-filling.

`call_logs.cost_usd` is deliberately excluded from client-facing list SQL (asserted by `tests/test_list_call_logs_projection.py`) — this is internal COGS. **Keep that exclusion**, and keep that test passing.

### 6.3 Tests

`tests/test_pricing_cascade.py`: all rates set; some rates set; no rates set → `None`; zero duration and zero usage; `USD_INR` override. Plus one assertion in the projection test that `cost_usd` is still absent from client list SQL.

---

## 7. Phase 2b — transfer and live tools as script-config toggles

Same script-config editor. Two independent toggles in a **Call actions** section. Built-in `end_call` is never behind a toggle.

This is deliberately **not** a department map, SIP URIs, warm transfer, or an HTTP tool runner. The model never chooses the destination number.

### 7.1 Migration `014` (plan originally said `013`)

`013` was consumed by the 2026 catalog refresh. Phase 2b shipped as **014**. Same two-file pattern.

```sql
ALTER TABLE script_configs
    ADD COLUMN IF NOT EXISTS transfer_enabled   BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS transfer_number    TEXT,
    ADD COLUMN IF NOT EXISTS live_tools_enabled BOOLEAN NOT NULL DEFAULT false;

-- Keep existing CMS tools working across the deploy.
UPDATE script_configs
   SET live_tools_enabled = true
 WHERE cascade_live_tools IS NOT NULL
   AND cascade_live_tools <> '[]'::jsonb;
```

That back-fill is required: without it, `build_push_lead_data_schema` would silently stop registering tools for every config that has them today.

Plumb the three columns through the same five files as §4.7.

### 7.2 Validation

`telephony.normalize_plivo_number` only prepends `+` — it does not validate. Use `phonenumbers` (already a dependency, and already used by `lead_upload/normaliser.py`) to parse and store E.164.

```
if transfer_enabled:      transfer_number must parse as a valid number → store E.164
else:                     transfer_number may be anything, including null (ignored)
if live_tools_enabled:    cascade_live_tools must be a non-empty list of {name, description, properties?}
```

Route-gated like §4.4.

### 7.3 Admin UI

**Transfer calling** — checkbox; when on, a `Transfer number` text input, plus a persistent warning: *Transfer is on. Enter a valid number and tell the agent in the system instruction when to call `transfer_call` — for example, when the caller asks for a human. The model does not choose the destination; it always dials this number.* Save is blocked when the toggle is on and the number is missing or invalid, matching the existing outcome-mapping pattern. **Do not** parse the prompt text to prove transfer was mentioned.

**Live tools** — replaces the unlabelled Advanced JSON dump with the same pattern: checkbox, then the existing `cascade_live_tools` editor, plus a warning: *Live tools are on. Define each tool here and name them in the system instruction, including when the agent must call them. `end_call` is always available.* Save is blocked when the toggle is on and the JSON is empty or invalid.

Both blocks hidden for `route !== 'cascaded'`.

### 7.4 Runtime and bot

```python
tools = [end_call_fn]
if runtime.live_tools_enabled:
    tools += schemas_from(runtime.live_tools)      # includes push_lead_data when present
if runtime.transfer_enabled and runtime.transfer_number:
    tools += [transfer_call_fn]                    # properties: optional `reason` only
```

When live tools are off, `push_lead_data` is **not** registered even if leftover JSON sits in the row. `transfer_call` takes no destination argument; the handler reads `runtime.transfer_number`.

### 7.5 Transfer mechanics and the billing rule (D4)

Cold transfer on Plivo: `POST /v1/Account/{auth}/Call/{uuid}/Transfer/` with a `<Dial>{number}</Dial>` legacy URL. Add a small `transfer_plivo_call(call_uuid, to_number)` helper to `telephony.py`, reusing `_plivo_auth()`.

Our websocket then dies, which fires `on_client_disconnected` → `task.cancel()` → `attach_pipeline_finalize`. That is the existing clean-end path, so post-call extraction and billing already run correctly — and because billed duration comes from the pipeline's `perf_counter`, **D4 is satisfied by the current behaviour**: the client is billed only up to the transfer. Post-transfer human talk time is Plivo carrier cost, not client credits.

Three things still need explicit handling:

1. **Outcome.** Add `Transferred` to `TERMINAL` and to `SYSTEM_OUTCOMES` in `call_outcomes.py`. Per §2.9, system outcomes are excluded from a script config's outcome buckets, so `validate_outcome_mapping` is unaffected and no existing config needs editing. `TERMINAL` membership means no retry is scheduled.
2. **Suppress the callback.** The eventual Plivo hangup webhook lands in `plivo_hangup.handle_plivo_hangup`, where `apply_callee_hangup_callback` (L107) may schedule a callback for a call that was successfully handed to a human. Transferred calls must skip that branch. The recovery branch is already safe: `in_progress` is false by then, so `_hangup_recover` will not fire.
3. **Signalling.** The transfer handler sets a flag on a small mutable holder passed into `attach_pipeline_finalize`, which forces `outcome="Transferred"` instead of the extracted `intent_status`.

`guides/onprem_airgap_architecture.md` warm transfer remains out of scope.

### 7.6 Tests

Toggle on with an invalid number → validation error. Toggle off with a garbage number → allowed and ignored. Tools on with `[]` → validation error. Runtime: the transfer tool is registered **iff** enabled; live tools **iff** enabled. Post-transfer: outcome is `Transferred`, billed duration equals pipeline duration, and no callback is scheduled.

---

## 8. Phase 3 — platform work

Do not mix into Phase 1–2b PRs.

### 8.1 BYOK

`cryptography` + `CLIENT_KEY_ENCRYPTION_KEY`; a `client_api_keys` table holding Fernet ciphertext that is never returned in plaintext on GET; admin UI on the client detail page; `providers/keys.py` checks DB then env — the `client_id`/`pool` parameters are already in place from §4.3, so this is a single-file change.

Note that `clients.api_key_hash` is the client's *auth token*, not a vendor key, and `pgcrypto` is loaded for `gen_random_uuid()`, not column encryption.

**BYOK changes margin.** `credits_per_minute` is documented in `001_initial.sql` as covering vendor cost plus markup. If a client brings their own keys, credits should cover telephony and platform fee only. Do not ship BYOK without that billing rule — likely a `bot_configs.byok` flag.

### 8.2 Telephony adapters

Only when a second carrier is actually scheduled. `telephony/` currently holds nothing but `__pycache__`, and creating `telephony/__init__.py` would **shadow** the root `telephony.py` that `server.py`, `recording.py`, and the dialer all import. Either keep root `telephony.py` as a compatibility shim, or rename (`mv telephony.py telephony_plivo.py`, then re-export from the package). Treat it as a real migration.

`parse_telephony_websocket()` already returns a `transport_type` (Pipecat detects `twilio` / `telnyx` / `plivo` / `exotel`) that `bot_cascade.py` L240 throws away — that is the seam for serializer selection. Answer XML (`server.py` 435–440) and hangup parsing belong on the adapter. Twilio/Telnyx/Exotel can start as stubs raising `NotImplementedError`.

---

## 9. Phase 4 — optional

- **Failover** (F10): `cascade_{stt,tts}_fallback_provider`; factory try/except on **init only**, never mid-call. After Phase 1 is stable.
- **Soniox**: add the `soniox` extra and `SONIOX_API_KEY` together with the catalog entries — not before.
- **Live catalog overlay**: see §10.
- **Webhook tools / SSRF allowlist**: explicitly not part of Phase 2b.

---

## 10. Live vendor catalogs — research

**Question:** if the Models tab pulled models live from each vendor, could that response also drive model-specific settings?

**Answer: partially.** Live APIs refresh *which models and voices exist*. They generally cannot say *which controls to render*, with min/max, required flags, or Pipecat constructor names. Two of seven vendors return a model list plus some capability flags; one (Gemini) returns real generation parameters; **zero** return a usable form schema. `providers/catalog.py` stays the source of truth.

| Vendor | Live model list | Live per-model settings | Detail |
|---|---|---|---|
| **ElevenLabs** | Yes — `GET /v1/models` | Partial | Returns `model_id`, `name`, `languages[]`, `can_do_text_to_speech`, `can_use_style`, `can_use_speaker_boost`, char limits. **No** speed capability flag or range — precisely the fact we need for `eleven_v3`. `GET /v1/voices` is account-specific and is the genuinely useful live picker. |
| **Deepgram** | Yes — `GET /v1/models` | Partial | `name`, `canonical_name`, `languages[]`, `streaming`, `batch`. Says nothing about `smart_format`, `punctuate`, or endpointing. Includes batch-only models we must not offer for telephony. |
| **Google Gemini** | Yes — `GET /v1beta/models` | Closest | `temperature`, `maxTemperature`, `topP`, `topK`, token limits, `supportedGenerationMethods`. Newer Flash models still *list* temperature but ignore it server-side. |
| **Groq** | Yes — `GET /openai/v1/models` | IDs only | `{id, created, object, owned_by}`. Mixes chat, Whisper, TTS, embeddings. No tool-calling flag. |
| **OpenAI** | Yes — `GET /v1/models` | IDs only | Same shape, same filtering problem. |
| **Cartesia** | **No** `/models` | No | Model IDs are an OpenAPI enum. `generation_config` ranges are documented in prose only. `GET /voices` is paginated and account-specific — viable live voice picker. |
| **Sarvam** | **No** list endpoint | No | OpenAPI enum. `mode` is saaras-only; Saarika v2.5 is legacy. |

**Why live-only fails:** vendor lists are not telephony-safe subsets (Groq ships Whisper, Deepgram ships batch-only STT, ElevenLabs ships music and SFX); capability flags are incomplete; the editor must work without vendor keys, since script config is platform-wide; and Pipecat's field names never appear in vendor JSON.

**Recommended hybrid, Phase 4.** Keep allowed providers, constructible model IDs, field keys/types/ranges/defaults, and the Pipecat mapping in `catalog.py`. Optionally overlay live *ids, display names, and languages*, and live **voice pickers** (`GET /v1/voices`, `GET /voices`) when a key exists, falling back to a text field otherwise. Cache in Redis with a ~1 hour TTL; on any failure serve `catalog.py` alone.

---

## 11. File checklists

### Phase 1a

| File | Change | Risk |
|---|---|---|
| `providers/catalog.py` | **New** — vendor/model/field data only | None |
| `providers/keys.py` | **New** — env lookup, BYOK-shaped signature | None |
| `providers/factory.py` | **New** — generic builder + service map | None |
| `script_runtime.py` | Providers, models, settings, voice on `CascadeRuntime`; catalog defaults; drop `sonic-3` fallback | Low |
| `bot_cascade.py` | Factory calls; log script_id + providers | **Medium** |
| `api/script_config_validation.py` | Route-gated catalog validation; `_SNAPSHOT_COLUMNS`; `_JSON_DICT_FIELDS`; `default_template` | Low |
| `api/routes/internal_script_configs.py` | 4 fields on both Pydantic models; `GET /internal/cascade-providers` | Low |
| `db/postgres.py` | INSERT list, `_SCRIPT_CONFIG_PATCHABLE`, `_SCRIPT_CONFIG_JSONB` | Low |
| `script_prefetch.py` | Forward model + 3 settings dicts; remove voice default | Low |
| `script_module_export.py` | Both export functions | Low |
| `db/schema/012_*.sql` + `alembic/versions/012_*.py` | New columns + `sonic-3` repair | Low |
| `env.example` | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Low |

### Phase 1b

| File | Change | Risk |
|---|---|---|
| `frontend/.../AdminScriptConfigs.jsx` | Cascading Models tab from the catalog API; prune settings on change; route-gate VAD and Gemini blocks | **Medium** |

### Phase 2

| File | Change | Risk |
|---|---|---|
| `pricing_cascade.py` | New | None |
| `call_transcript.py` | Route dispatch; `providers` param; `cost_usd` into usage summary | Low |
| `db/postgres.py` `finalize_call_log` | Write `cost_usd` from `usage` | Low |

### Phase 2b

| File | Change | Risk |
|---|---|---|
| `db/schema/013_*.sql` + `alembic/versions/013_*.py` | 3 columns + live-tools back-fill | Low |
| `api/script_config_validation.py` | E.164 via `phonenumbers`; tools JSON | Low |
| `script_runtime.py` / `script_prefetch.py` | Pass toggles and number | Low |
| `bot_cascade.py` | Conditional tool registration; transfer handler | **Medium** |
| `telephony.py` | `transfer_plivo_call` helper | Medium |
| `plivo_hangup.py` | Suppress callback scheduling for transferred calls | Medium |
| `call_outcomes.py` | `Transferred` → `TERMINAL` + `SYSTEM_OUTCOMES` | Low |
| `frontend/.../AdminScriptConfigs.jsx` | Two toggles, number field, tools JSON, warnings | Low |

### Unchanged throughout Phases 1–2b

`call_limits.py`, `call_metrics.py`, `lead_context.py`, `billing.py`, `post_call_processor.py`, `bot_sts.py`, `recording.py`, `server.py`.

---

## 12. Corrections to plan v2

| v2 claim | Reality |
|---|---|
| "Pipecat constructors are not uniform; use explicit per-vendor builders" | Settings are uniform and share a base with `from_mapping()`. ElevenLabs uses `voice`, not `voice_id`. The sample code used deprecated constructor kwargs. |
| "Alembic plus a matching `db/schema/` file *if that folder is still used*" | The migration **executes** that file. It is mandatory, path-relative, and cannot contain `DO` blocks. |
| `sonic-3`-as-voice is a schema default plus a repair | Seven code sites write it (F20). |
| Validation is a self-contained addition | PATCH validates the whole merged row, so it applies retroactively to every config including STS (F26). |
| `providers/` needs six files | Three, under D1. |
| Phase 2b transfer is a UI plus a REST call | Also needs an outcome, callback suppression, and a signalling path (§7.5). |
| `cost_usd` needs new plumbing through `finalize_call_log` | The `usage` dict already reaches both call sites; one line each. |

---

## 13. Out of scope

- Changing STS / Gemini Live provider selection
- Replacing Plivo as the production carrier
- Warm transfer, SIP queues, multi-target transfer maps
- Generic webhook / `handler_type` tool runner (Phase 2b live tools are LLM schemas only)
- Distributed dialer / Celery (`future_updates.md` §1–2)
- OpenInference / Sentry (`future_updates.md` §6)
- Rewriting `push_lead_data` to replace post-call extraction (F24: the handler only logs; `post_call_extract` remains the source of truth)

---

## 14. Estimates

| Phase | Estimate |
|---|---|
| 1a — backend last mile | 2–3 days |
| 1b — Models tab | 1–2 days |
| 2 — cascade COGS | ~1 day |
| 2b — transfer + live tools | 1.5–2 days |
| 3 — BYOK and telephony | Weeks; split by product |

Do not quote Phase 3 as part of a single deliverable.

---

## 15. Implementation log

### Phase 1a — completed 2026-08-19

**Status:** Shipped (backend). Deployable with today's free-text Models tab; run `alembic upgrade head` from repo root before use.

**Files created:**
- `providers/__init__.py` — package marker
- `providers/catalog.py` — STT/LLM/TTS catalogs, helpers, `catalog_as_json()`
- `providers/keys.py` — async env key resolution (BYOK-shaped signature)
- `providers/factory.py` — generic Pipecat service builder for all 7 provider/kind pairs
- `db/schema/012_cascade_provider_settings.sql` — `cascade_tts_model`, 3 settings JSONB columns, F20 voice repair
- `alembic/versions/012_cascade_provider_settings.py` — migration loader (head after `011`)
- `tests/test_provider_catalog.py` — catalog integrity + Pipecat field introspection
- `tests/test_provider_factory.py` — factory builds, nested keys, ctor routing, voice fallback
- `tests/test_provider_validation.py` — route-gated validation + D2 STS regression
- `tests/test_cascade_runtime_providers.py` — prefetch → `CascadeRuntime` wiring

**Files modified:**
- `script_runtime.py` — `CascadeRuntime` carries providers/models/settings/`live_tools`; catalog defaults; F20 voice collapse
- `bot_cascade.py` — factory replaces hardcoded Sarvam/Groq/Cartesia; script_id + provider/model logging (F23)
- `api/script_config_validation.py` — `validate_cascade_config()` (D2 gated); snapshot/JSONB/template updates
- `api/routes/internal_script_configs.py` — 4 new Pydantic fields; `GET /internal/cascade-providers`
- `db/postgres.py` — INSERT/PATCHABLE/JSONB for 4 new columns; voice default `""`
- `script_prefetch.py` — forward model + settings; remove `sonic-3` voice default
- `script_module_export.py` — voice `""`, model `"sonic-3"`, empty settings in both exports
- `env.example` — `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`
- `tests/test_script_runtime.py` — assert provider fields on prefetch hit
- `tests/test_script_prefetch.py` — assert new keys forwarded

**Deviations from plan:**
- OpenAI settings import uses `pipecat.services.openai.base_llm.OpenAILLMSettings` (not `openai.llm`) per Pipecat 1.5.0 layout
- LLM catalog models: groq (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.6-27b`), openai (`gpt-4o-mini`, `gpt-4o`), google (`gemini-3.6-flash`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-3.5-flash`)
- Sarvam `mode` stored on service `_mode` attribute (verified via factory test, not mock)
- Live `eleven_v3` 8 kHz smoke call **not** run — required before production release (§4.2 checklist)

**Verification:**
- `pytest tests/test_provider_*.py tests/test_cascade_runtime_providers.py tests/test_script_runtime.py tests/test_script_prefetch.py tests/test_script_config_validation.py tests/test_script_module_export.py` — **69 passed** (2026-08-19)
- Migration 012 not applied in CI/dev here; run `alembic upgrade head` from repo root against Postgres

**Findings addressed:**
- F1, F2, F3, F5, F7, F17, F19 (partial — API only), F20 (all 7 sites + migration repair), F21 (via settings JSONB)

**Remaining for Phase 1b:**
- `frontend/src/admin/pages/AdminScriptConfigs.jsx` — catalog-driven Models tab consuming `GET /internal/cascade-providers`
- Provider/model change → settings prune UX
- Route-gate VAD block and Gemini fields for cascade configs

### Catalog refresh — 2026 voice-agent models (2026-08-20)

**Status:** Shipped (backend). Run `alembic upgrade head` for migration 013 (rewrites legacy model IDs in existing rows).

**Included (Pipecat 1.5.0 verified):**

| Role | Provider | Models |
|------|----------|--------|
| STT | Sarvam | `saaras:v3` (default), `saaras:v2.5` — `saaras:v4` deferred until Pipecat > 1.5.0 |
| STT | Soniox | `stt-rt-v5` |
| STT | ElevenLabs | `scribe_v2_realtime` |
| STT | Deepgram | `nova-3` |
| TTS | Cartesia | `sonic-3.5` (default), `sonic-3` |
| TTS | ElevenLabs | `eleven_flash_v2_5`, `eleven_flash_v2`, `eleven_v3` |
| TTS | Deepgram | `aura-2-thalia-en`, `aura-2-helena-en`, `aura-2-odysseus-en`, `aura-2-arcas-en` |
| TTS | Sarvam | `bulbul:v3` |
| TTS | Soniox | `tts-rt-v1` |

**Excluded (documented, not implemented):**
- Google Chirp 3 STT / Chirp HD / Gemini TTS — requires `GOOGLE_APPLICATION_CREDENTIALS`, not `GOOGLE_API_KEY`
- Deepgram Flux STT/TTS — `DeepgramFluxSTTService` and `/v2/speak` not in Pipecat 1.5.0
- Legacy: `saarika:v2.5`, `nova-2`, `eleven_turbo_v2_5`, `eleven_multilingual_v2`, `bulbul:v2`, ElevenLabs Scribe v2 batch

**Default migrations (013):** `saarika:v2.5` → `saaras:v3`; `sonic-3` → `sonic-3.5`; `nova-2` → `nova-3`; `eleven_turbo_v2_5` / `eleven_multilingual_v2` → `eleven_flash_v2_5`; `gemini-2.0-flash*` → `gemini-3.6-flash`; `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` / `mixtral-8x7b-32768` → `openai/gpt-oss-120b`.

**Recommended voices (Phase 1b pickers via `catalog_as_json().recommended_voices`):**

| Provider | Hindi / locale | Voices |
|----------|----------------|--------|
| Cartesia | hi-IN | Hindi Reporter Man, Hindi Calm Man, Hindi Narrator Woman, Indian Lady |
| Sarvam | hi-IN | shubh, ashutosh, priya, suhani |
| ElevenLabs | en (+ hi via language) | Rachel, Adam — **platform defaults expire Dec 2026**; prefer account Voice Library |
| Deepgram Aura-2 | en only | Thalia, Helena, Odysseus, Arcas |
| Soniox | en | Adrian, Mina |

**Notes:**
- Cartesia `sonic-3.5`: speed/volume fields disabled in catalog (emotion only); use `sonic-3` if speed control needed
- Deepgram TTS: model ID is the voice (`voice_mode=deepgram_model` in factory)
- Sarvam TTS: speaker name in `voice` / `SARVAM_TTS_SPEAKER`
- Env: `SONIOX_API_KEY` (STT+TTS), `SARVAM_TTS_SPEAKER`, `soniox` pipecat extra in `pyproject.toml`

**Files created:** `db/schema/013_catalog_2026_refresh.sql`, `alembic/versions/013_catalog_2026_refresh.py`

**Files modified:** `providers/catalog.py`, `providers/factory.py`, defaults in prefetch/validation/postgres/export/routes, `env.example`, `pyproject.toml`, provider tests

### Phase 1b — catalog-driven Models tab (2026-08-20)

**Status:** Shipped (frontend). Requires Phase 1a backend + catalog refresh; no new migrations.

**Files created:**
- `frontend/src/admin/lib/cascadeCatalog.js` — prune/default/lookup helpers, save validation, voice sync on load
- `frontend/src/admin/components/CascadeModelsPanel.jsx` — three-column STT/LLM/TTS UI driven by `GET /internal/cascade-providers`

**Files modified:**
- `frontend/src/admin/pages/AdminScriptConfigs.jsx` — catalog fetch on editor open; `CascadeModelsPanel` for `route === "cascaded"`; settings prune via `updateCascadeRole`; client-side block on stale catalog values; VAD block STS-only (F22)
- `frontend/src/admin/pages/AdminScriptConfigs.css` — grid, role column, key warning, legacy banner, voice chip styles

**Behaviour:**
- Provider/model/settings rendered entirely from catalog JSON — no hardcoded vendor names in JSX
- Provider change → reset model to `default_model` + fresh settings defaults
- Model change → prune settings keys absent from new field list; apply defaults for new fields
- TTS `cascade_tts_voice` kept in sync with catalog `voice` field; Deepgram Aura-2 uses model ID as voice (no separate control)
- Recommended voice chips from `recommended_voices` per TTS model
- Missing API key → inline warning via `key_configured` (no env name leaked)
- Legacy/stale provider or model → amber banner + save blocked until re-picked

**Route gating:**
- STS Models tab: Gemini fields + VAD only
- Cascaded Models tab: cascade panel only (no Gemini, no VAD)

**Manual QA:** See plan checklist (12 cases); no frontend unit-test runner added.

**Optimized cascade boilerplate:** `catalog.default_cascade_boilerplate()` pre-fills new cascaded templates with Hindi outbound presets — Sarvam STT `hi-IN`, Groq LLM `openai/gpt-oss-120b` with `temperature=0.2` / `max_tokens=512`, Cartesia TTS `sonic-3.5` + Hindi Narrator Woman voice. Used by `default_template("cascaded")` and `export_cascade_module()`.

### LLM deprecation fix — Groq + Google (2026-08-20)

**Root cause (live test calls):** Groq retired `llama-3.3-70b-versatile` (Aug 16, 2026); Google API returns 404 for `gemini-2.0-flash` with message to use `gemini-3.6-flash`.

**Catalog defaults updated:**
- Groq default → `openai/gpt-oss-120b` (also `openai/gpt-oss-20b`, `qwen/qwen3.6-27b`)
- Google default → `gemini-3.6-flash`

**Also updated:** `POST_CALL_MODEL` default in `env.example` / `post_call_extract.py`; script-config defaults; migration 013 rewrites for stored rows.

**Action required:** Run `uv run alembic upgrade head` so existing script configs (e.g. provwave with `gemini-2.0-flash`) pick up new model IDs. Or re-save the script in admin after picking LLM from the catalog.

### Phase 2 — cascade COGS (2026-08-23)

**Status:** Shipped (backend). No schema migration. Internal COGS only — not shown on client list/detail.

**Design:** Per-provider env rates (`STT_{PROVIDER}_USD_PER_MIN`, `LLM_{PROVIDER}_INPUT_USD_PER_1M` / `OUTPUT`, `TTS_{PROVIDER}_USD_PER_1K_CHARS`). STT minutes from pipeline wall-clock. If no component rate is set → `None`; if any is set, missing components count as `$0`. `compute_sts_cost_inr` signature unchanged. FX helper `usd_inr_rate()` in `pricing_sts.py`.

**Files created:** `pricing_cascade.py`

**Files modified:**
- `bot_cascade.py` — passes `{stt, llm, tts}` into `attach_pipeline_finalize`
- `call_transcript.py` — route dispatch; inject `cost_usd` into usage **before** SQLite dump
- `db/postgres.py` `finalize_call_log` — `cost_usd = COALESCE($14, cost_usd)` (empty recovery `usage={}` cannot wipe a stored value)
- `public_call_detail` — strips `cost_usd` (client GET stays COGS-clean; list SQL already omitted it)
- `env.example` — commented rate stubs per catalog provider
- `tests/test_pricing_cascade.py` plus projection / detail / STS signature guards

**Findings addressed:** F6, F25

**Out of scope (still):** per-model rates, telephony COGS, admin margin charts, writing cascade `cost_inr` to SQLite/n8n.

### Phase 2b — transfer + live tools (2026-08-23)

**Status:** Shipped. Run `alembic upgrade head` for migration **014** (`013` was already the catalog refresh).

**Behaviour:**
- `end_call` always registered
- Live tools (including `push_lead_data`) register **only** when `live_tools_enabled` is true. 014 back-fills that flag for rows with non-empty `cascade_live_tools`, so existing CMS tools keep working. Empty-JSON configs lose the hardcoded default tool unless the operator turns the toggle on.
- `transfer_call` takes optional `reason` only; destination is `runtime.transfer_number` (E.164). Model never chooses the number.
- Cold Plivo transfer: Redis Dial XML at `GET /plivo-transfer-xml?session_call_id=` (destination not in the query string) → `telephony.transfer_plivo_call`. Websocket death → existing finalize. D4: billed duration is pipeline `perf_counter`.
- Outcome `Transferred` added to `TERMINAL` + `SYSTEM_OUTCOMES`. `attach_pipeline_finalize` forces `extraction["intent_status"] = "Transferred"` when the transfer holder is set. `apply_early_disconnect_policy` does not rewrite it (not a weak status). Hangup skips callee-callback when Redis `transfer:{session}` or `call_data.transferred` is set.

**Files created:**
- `db/schema/014_cascade_call_actions.sql` + `alembic/versions/014_cascade_call_actions.py`
- `call_transfer.py` — Redis store/lookup for Dial XML
- `tests/test_cascade_call_actions.py`

**Files modified:**
- `db/postgres.py` — INSERT/PATCHABLE for 3 columns; `mark_call_transferred`
- `api/script_config_validation.py` — E.164 via `phonenumbers`; live-tools JSON; snapshot/template
- `api/routes/internal_script_configs.py` — 3 fields on both Pydantic models
- `script_prefetch.py` / `script_module_export.py` / `script_runtime.py` — toggles + number on `CascadeRuntime`
- `bot_cascade.py` — `cascade_tool_schemas`; transfer handler; generic log-only live-tool handler
- `telephony.py` — `transfer_plivo_call` + `build_transfer_xml_url`
- `server.py` — `GET /plivo-transfer-xml`
- `call_transcript.py` — `transfer_state` + `apply_transfer_outcome`
- `call_outcomes.py` — `Transferred`
- `plivo_hangup.py` — skip callback on transferred calls
- `frontend/src/admin/pages/AdminScriptConfigs.jsx` — Call actions toggles, warnings, save-block; hidden unless `route === "cascaded"`

**Findings addressed:** F14, F15 (toggle + JSON only; webhook runner still Phase 4 / out of scope)

**Unchanged (as planned):** `billing.py`, `bot_sts.py`, `call_limits.py`, `post_call_processor.py`

### Cascade default template + scripting guide (2026-08-23)

**Status:** Shipped (follows Phase 2b). Makes new cascaded CMS rows transfer-**script**-ready without turning transfer on (that still needs an E.164 number).

**Default template** (`GET /internal/script-configs/template?route=cascaded`):
- `script_id`: `cascade_outbound`
- Hindi outbound STT/LLM/TTS presets (unchanged from 1b boilerplate)
- `live_tools_enabled: true` + `push_lead_data` schema from `PYRAMID_CASCADE_LIVE_TOOLS`
- `transfer_enabled: false` (operator sets number in Call actions)
- System instruction documents `end_call` / `push_lead_data` / `transfer_call` protocol (hold line → tool → stop; no destination arg)

**Guide:**
- `frontend/src/admin/components/CascadeScriptingGuideModal.jsx` — separate from the STS guide. Editor button reads **Cascade Guide** when `route === "cascaded"`.
- Tabs: tools & transfer, CMS fields, stack & toggles, outcomes (`Transferred` is system, not an extraction enum)
- Copy-for-AI prompt is cascade-only (not Gemini Live)
- Written copy: `guides/admin_cascade_script_guide.md`

**Files created:** `cascade_scripts/cms_default.py`, `frontend/src/admin/components/CascadeScriptingGuideModal.jsx`, `guides/admin_cascade_script_guide.md`

**Files modified:** `api/script_config_validation.py` `default_template("cascaded")`; `script_module_export.py` sets `live_tools_enabled` when module `CASCADE_LIVE_TOOLS` is non-empty; `AdminScriptConfigs.jsx` route-picks the guide modal

