import socket
import threading
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest
import uvicorn
from sqlalchemy.schema import DropSchema
from stubs.main import create_app
from stubs.migrate import upgrade
from stubs.store import Settings
from stubs.store import database as stub_database

from app.modules.payments.adapter import StubAdapter


@pytest.fixture
def gateway(application, settings, database):
    stub_settings = Settings(
        _env_file=None,
        database_url=settings.database_url,
        stub_schema=settings.database_schema + "_stub",
        payment_stub_key=uuid4().hex + uuid4().hex,
        public_app_url="http://testserver",
        stub_timeout_seconds=2.0,
    )
    upgrade(stub_settings)
    engine, sessions = stub_database(stub_settings)
    state = SimpleNamespace(
        server=None, thread=None, port=0, stub_settings=stub_settings, sessions=sessions
    )

    def start():
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", state.port))
        sock.listen(128)
        state.port = sock.getsockname()[1]
        state.server = uvicorn.Server(
            uvicorn.Config(create_app(stub_settings), log_level="critical", access_log=False)
        )
        state.thread = threading.Thread(
            target=state.server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        state.thread.start()
        deadline = time.monotonic() + 15
        while not state.server.started:
            if time.monotonic() > deadline or not state.thread.is_alive():
                raise AssertionError("Payment simulator did not start")
            time.sleep(0.01)

    def stop():
        if state.server is not None:
            state.server.should_exit = True
            state.thread.join(timeout=10)
            assert not state.thread.is_alive()

    start()
    state.url = f"http://127.0.0.1:{state.port}"
    state.crm_settings = settings.model_copy(
        update={
            "payment_stub_url": state.url,
            "payment_stub_key": stub_settings.payment_stub_key,
            "public_app_url": "http://testserver",
            "payment_timeout_seconds": 1.0,
        }
    )
    application.state.payment_adapter = StubAdapter(state.crm_settings)
    state.adapter = application.state.payment_adapter
    state.restart = lambda: (stop(), start())

    def outcome(payment, value):
        assert isinstance(payment["payment_url"], str), (
            "Reconcile the payment before choosing an outcome"
        )
        with httpx.Client(trust_env=False, timeout=5) as connection:
            return connection.post(
                state.url + urlsplit(payment["payment_url"]).path,
                data={"outcome": value},
                headers={"Origin": "http://testserver"},
            )

    state.outcome = outcome
    try:
        yield state
    finally:
        stop()
        engine.dispose()
        with database.engine.begin() as connection:
            connection.execute(DropSchema(stub_settings.stub_schema, cascade=True))
