"""Smoke tests for client events API wiring."""

from __future__ import annotations


def test_events_router_imports_request_bodies():
    from api.routes import events

    assert events.PatchEventBody is not None
    assert events.CreateOutcomeMappingBody is not None


def test_events_openapi_includes_patch_route():
    import server

    schema = server.app.openapi()
    assert "/api/events/{event_id}" in schema["paths"]
    patch = schema["paths"]["/api/events/{event_id}"]["patch"]
    assert patch["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "PatchEventBody"
    )
