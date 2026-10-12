"""Authenticated binary-only HTTP boundary for the optional private parser."""
from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from services.document_parser.worker import MAX_BYTES, ParserFailure, ParserProcess


def create_app(parser=None) -> FastAPI:
    engine = parser or ParserProcess()
    admission = asyncio.Semaphore(1)

    @asynccontextmanager
    async def lifespan(app):
        if parser is None:
            engine.start()
            # Initial model load is outside request latency. Health is not ready
            # until it completes; an absent model bundle never downloads itself.
            await asyncio.to_thread(engine.ready, 120)
        try:
            yield
        finally:
            engine.close()

    app = FastAPI(title='Private document parser', lifespan=lifespan, docs_url=None,
                  redoc_url=None, openapi_url=None)

    def authorize(request: Request):
        token = os.getenv('LEGAL_DOCUMENT_PARSER_TOKEN', '').strip()
        if len(token) < 32 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise HTTPException(503, detail='parser_unconfigured')
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
            raise HTTPException(401, detail='unauthorized')

    @app.get('/healthz')
    async def health(request: Request):
        authorize(request)
        ready = engine.ready()
        return JSONResponse({'version': 1, 'ready': ready}, status_code=200 if ready else 503)

    @app.post('/v1/parse')
    async def parse(request: Request):
        authorize(request)
        if request.query_params or request.headers.get('x-parser-protocol') != '1':
            raise HTTPException(400, detail='unsupported_protocol')
        media_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if media_type not in ('application/pdf', 'image/png', 'image/jpeg', 'image/tiff', 'image/webp'):
            raise HTTPException(415, detail='unsupported_type')
        if request.headers.get('content-encoding', 'identity') != 'identity':
            raise HTTPException(415, detail='unsupported_encoding')
        try:
            length = int(request.headers.get('content-length', '0'))
            if length < 0 or length > MAX_BYTES:
                raise ValueError
        except ValueError:
            raise HTTPException(413, detail='input_limit') from None
        if not engine.ready():
            raise HTTPException(503, detail='parser_unavailable')
        if admission.locked():
            raise HTTPException(429, detail='parser_busy')
        async with admission:
            return await read_and_convert(request, media_type)

    async def read_and_convert(request: Request, media_type: str):
        data = bytearray()
        try:
            async with asyncio.timeout(10):
                async for chunk in request.stream():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise HTTPException(413, detail='input_limit')
        except TimeoutError:
            raise HTTPException(408, detail='upload_timeout') from None
        if not data:
            raise HTTPException(400, detail='empty_input')
        try:
            result = await asyncio.to_thread(engine.convert, bytes(data), media_type)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ParserFailure as exc:
            status = {'busy': 429, 'timeout': 504, 'input_limit': 413, 'unsupported_type': 415}.get(exc.code, 503)
            raise HTTPException(status, detail='parser_' + exc.code) from None
        except Exception:
            raise HTTPException(503, detail='parser_unavailable') from None

    return app


app = create_app()
