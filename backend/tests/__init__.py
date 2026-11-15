"""Tests, split by what they need.

test_wer.py, test_audio.py, test_degrade.py
    Pure unit tests. No network, no API key, no audio device. These run in CI
    on every push and are the ones to extend when you change DSP or metrics.

test_server.py
    Integration: boots the aiohttp app in-process and drives it over a real
    websocket. Microphone and TTS are stubbed, so it needs no key either. It
    fails when a message type, route or the half-duplex rule breaks.

test_live_api.py
    Real API calls. Skipped unless RUN_LIVE=1. Never runs in CI — it costs
    credits.
"""
