"""Raw ESC/POS passthrough for network (LAN) receipt printers — iter411.

A browser cannot open a TCP socket, so a till with a network printer sends the
receipt bytes here and the server forwards them to the printer's own port
(9100 on every thermal printer worth having).

Only private/link-local addresses are accepted: this endpoint must never become
a way to make the server knock on arbitrary hosts.
"""
import asyncio
import base64
import ipaddress
import socket

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user, logger

router = APIRouter(prefix="/api/pos", tags=["pos"])

MAX_JOB_BYTES = 256 * 1024


class RawPrintJob(BaseModel):
    host: str
    port: int = 9100
    data_b64: str


def _assert_lan(host: str) -> str:
    """Resolve and refuse anything that is not on a private network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Cannot find a printer at '{host}' on this network")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            raise HTTPException(
                status_code=400,
                detail="Only a printer on your own network can be used (its address must be a local one).",
            )
    return infos[0][4][0]


@router.post("/print-raw")
async def print_raw(job: RawPrintJob, current_user: dict = Depends(get_current_user)) -> dict:
    if not 1 <= job.port <= 65535:
        raise HTTPException(status_code=400, detail="Printer port must be between 1 and 65535")
    try:
        payload = base64.b64decode(job.data_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Print job was not valid data")
    if not payload:
        raise HTTPException(status_code=400, detail="Nothing to print")
    if len(payload) > MAX_JOB_BYTES:
        raise HTTPException(status_code=413, detail="That receipt is too large to print")

    ip = _assert_lan(job.host)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, job.port), timeout=5)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"The printer at {job.host}:{job.port} did not answer")
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach the printer at {job.host}:{job.port} ({exc.strerror or exc})")
    try:
        writer.write(payload)
        await asyncio.wait_for(writer.drain(), timeout=5)
    except (OSError, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"The printer stopped responding mid-receipt ({exc})")
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except (asyncio.TimeoutError, OSError):
            pass
    logger.info("POS raw print: %s bytes to %s:%s by %s", len(payload), job.host, job.port, current_user.get("email"))
    return {"sent": True, "bytes": len(payload)}
