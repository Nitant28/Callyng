"""Cascade route must end user turns on VAD silence, not Smart Turn."""

from __future__ import annotations

from bot_cascade import (
    CASCADE_SPEECH_TIMEOUT_S,
    CASCADE_VAD_PARAMS,
    cascade_kickoff_messages,
    cascade_user_aggregator_params,
    cascade_user_turn_strategies,
)
from pipecat.turns.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy
from pipecat.turns.user_start import (
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from providers.factory import TELEPHONY_SAMPLE_RATE


def test_cascade_vad_catches_short_hindi_replies():
    assert CASCADE_VAD_PARAMS.start_secs <= 0.1
    assert CASCADE_VAD_PARAMS.stop_secs == 0.2
    assert CASCADE_VAD_PARAMS.min_volume <= 0.4
    assert CASCADE_VAD_PARAMS.confidence <= 0.5


def test_cascade_stop_strategy_is_speech_timeout_not_smart_turn():
    strategies = cascade_user_turn_strategies()
    assert len(strategies.start) == 2
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert isinstance(strategies.start[1], TranscriptionUserTurnStartStrategy)
    assert len(strategies.stop) == 1
    stop = strategies.stop[0]
    assert isinstance(stop, SpeechTimeoutUserTurnStopStrategy)
    assert stop._user_speech_timeout == CASCADE_SPEECH_TIMEOUT_S


def test_telephony_sample_rate_is_8khz():
    assert TELEPHONY_SAMPLE_RATE == 8000


def test_cascade_kickoff_is_step1_only():
    msgs = cascade_kickoff_messages("Rama")
    assert msgs[0]["role"] == "user"
    assert "Rama" in msgs[0]["content"]
    assert "Step 1" in msgs[0]["content"]
    assert "stop and wait" in msgs[0]["content"]


def test_cascade_mutes_until_first_bot_complete():
    params = cascade_user_aggregator_params()
    assert len(params.user_mute_strategies) == 1
    assert isinstance(
        params.user_mute_strategies[0],
        MuteUntilFirstBotCompleteUserMuteStrategy,
    )
