# iter411: network (LAN) receipt printers — the browser cannot open a socket, so
# the receipt bytes are forwarded by the server to the printer's own port.
import asyncio
import base64
import sys

import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")

from fastapi import HTTPException  # noqa: E402
from routers.pos_print import RawPrintJob, print_raw  # noqa: E402

USER = {"id": "test-cashier", "role": "Staff", "email": "till@test.local"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _job(**over):
    return RawPrintJob(**{"host": "127.0.0.1", "port": 9100, "data_b64": base64.b64encode(b"hello").decode(), **over})


def test_it_reaches_a_printer_listening_on_the_network():
    received = {}

    async def scenario():
        async def handle(reader, writer):
            received["bytes"] = await reader.read(1024)
            writer.close()
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            out = await print_raw(_job(port=port, data_b64=base64.b64encode(b"\x1b@RECEIPT").decode()), USER)
            await asyncio.sleep(0.1)
            return out

    out = _run(scenario())
    assert out["sent"] is True
    assert received["bytes"] == b"\x1b@RECEIPT"


def test_a_printer_that_is_not_there_says_so_plainly():
    with pytest.raises(HTTPException) as e:
        _run(print_raw(_job(port=9099), USER))
    assert e.value.status_code in (502, 504)
    assert "printer" in e.value.detail.lower()


def test_it_refuses_to_knock_on_hosts_outside_your_network():
    """This endpoint must never become a way to make the server call out."""
    with pytest.raises(HTTPException) as e:
        _run(print_raw(_job(host="example.com", port=80), USER))
    assert e.value.status_code == 400
    assert "own network" in e.value.detail


def test_an_empty_job_is_rejected():
    with pytest.raises(HTTPException) as e:
        _run(print_raw(_job(data_b64=""), USER))
    assert e.value.status_code == 400


def test_a_silly_big_job_is_rejected():
    big = base64.b64encode(b"x" * (300 * 1024)).decode()
    with pytest.raises(HTTPException) as e:
        _run(print_raw(_job(data_b64=big), USER))
    assert e.value.status_code == 413


def test_rubbish_data_is_rejected():
    with pytest.raises(HTTPException) as e:
        _run(print_raw(_job(data_b64="not base64 at all!!"), USER))
    assert e.value.status_code == 400
