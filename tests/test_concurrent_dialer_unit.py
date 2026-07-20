import asyncio
import uuid
import pytest
from dialer.concurrent_dialer import (
    stop_dialer,
    shutdown_all_dialers,
    _active_tasks,
    _campaign_key,
)

@pytest.mark.asyncio
async def test_stop_dialer_robustness():
    """BUG-05/BUG-37 unit test: asserts task is cancelled, awaited, and state is cleaned up."""
    campaign_id = uuid.uuid4()
    client_id = uuid.uuid4()
    key = _campaign_key(campaign_id, client_id)

    class MockApp:
        class State:
            dialer_tasks = {}
        state = State()

    app = MockApp()
    
    lock_released = False

    async def fake_dialer_runner():
        nonlocal lock_released
        try:
            # Simulate dialer waiting
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        finally:
            lock_released = True
            # Simulate the cleanup that happens in _runner and run_campaign_dialer finally blocks
            if _active_tasks.get(key) is task:
                _active_tasks.pop(key, None)
            if app.state.dialer_tasks.get(key) is task:
                app.state.dialer_tasks.pop(key, None)

    task = asyncio.create_task(fake_dialer_runner())
    
    # Inject fake task into both registries
    _active_tasks[key] = task
    app.state.dialer_tasks[key] = task

    # Yield to let the task start
    await asyncio.sleep(0.01)

    # Call stop_dialer
    await stop_dialer(campaign_id, client_id)

    # Assertions
    assert task.cancelled()
    assert lock_released is True
    assert key not in _active_tasks
    assert key not in app.state.dialer_tasks


@pytest.mark.asyncio
async def test_shutdown_all_dialers():
    campaign_id = uuid.uuid4()
    client_id = uuid.uuid4()
    key = _campaign_key(campaign_id, client_id)

    class MockApp:
        class State:
            dialer_tasks = {}
        state = State()

    app = MockApp()
    started = asyncio.Event()

    async def fake_dialer_runner():
        started.set()
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        finally:
            _active_tasks.pop(key, None)

    task = asyncio.create_task(fake_dialer_runner())
    _active_tasks[key] = task
    app.state.dialer_tasks[key] = task
    await started.wait()

    await shutdown_all_dialers(app)

    assert task.done()
    assert key not in app.state.dialer_tasks
    assert key not in _active_tasks
