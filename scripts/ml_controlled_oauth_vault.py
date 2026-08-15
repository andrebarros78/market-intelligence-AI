from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

APP_ID = "3438551912770538"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
API_BASE = "https://api.mercadolibre.com"
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8771
CLIENT_SECRET_TARGET = "MarketIntelligenceAI/MercadoLivre/ClientSecret"
ACCESS_TARGET = "MarketIntelligenceAI/MercadoLivre/ControlledWriteToken"
REFRESH_TARGET = "MarketIntelligenceAI/MercadoLivre/ControlledWriteRefreshToken"
META_TARGET = "MarketIntelligenceAI/MercadoLivre/ControlledWriteOAuthMeta"

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
_advapi32.CredWriteW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]
_advapi32.CredFree.restype = None


def cred_read(target: str) -> str | None:
    ptr = ctypes.c_void_p()
    if not _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        return None
    try:
        cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIALW)).contents
        size = int(cred.CredentialBlobSize)
        if not cred.CredentialBlob or size <= 0:
            return None
        raw = ctypes.string_at(cred.CredentialBlob, size)
        return raw.decode("utf-16-le")
    finally:
        _advapi32.CredFree(ptr)


def cred_write(target: str, secret: str, username: str = "market-intelligence-ai") -> None:
    raw = secret.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    cred = CREDENTIALW()
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.UserName = username
    cred.CredentialBlobSize = len(raw)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    if not _advapi32.CredWriteW(ctypes.byref(cred), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    for i in range(len(buf)):
        buf[i] = 0


def _scope_set(raw: object) -> set[str]:
    if isinstance(raw, str):
        return {p.strip().lower() for p in raw.replace(",", " ").split() if p.strip()}
    if isinstance(raw, list):
        return {str(p).strip().lower() for p in raw if str(p).strip()}
    return set()


def validate_and_store_token(payload: dict[str, object], client: httpx.Client) -> None:
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    scopes = _scope_set(payload.get("scope"))
    if not isinstance(access, str) or not access:
        raise RuntimeError("oauth_access_token_missing")
    if not isinstance(refresh, str) or not refresh:
        raise RuntimeError("oauth_refresh_token_missing")
    if "read" not in scopes or "write" not in scopes:
        raise RuntimeError("oauth_read_write_scope_required")
    me = client.get(f"{API_BASE}/users/me", headers={"Authorization": f"Bearer {access}", "Accept": "application/json"})
    if me.status_code != 200:
        raise RuntimeError(f"users_me_http_{me.status_code}")
    body = me.json()
    if not isinstance(body, dict) or not body.get("id"):
        raise RuntimeError("users_me_identity_missing")
    token_user = payload.get("user_id")
    if token_user is not None and str(token_user) != str(body.get("id")):
        raise RuntimeError("oauth_user_binding_mismatch")
    try:
        lifetime = int(expires_in or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("oauth_expiry_invalid") from exc
    if lifetime <= 0:
        raise RuntimeError("oauth_expiry_invalid")
    cred_write(ACCESS_TARGET, access)
    cred_write(REFRESH_TARGET, refresh)
    meta = {
        "app_id": APP_ID,
        "expires_at_epoch": int(time.time()) + lifetime,
        "scopes": sorted(scopes),
        "user_hash": hashlib.sha256(str(body["id"]).encode("utf-8")).hexdigest(),
    }
    cred_write(META_TARGET, json.dumps(meta, separators=(",", ":")))
    print("OAUTH_TOKEN_VALIDATED=True")
    print("OAUTH_SCOPE_READ=True")
    print("OAUTH_SCOPE_WRITE=True")
    print("TOKEN_SAVED_TO_WINDOWS_VAULT=True")
    print("REFRESH_TOKEN_SAVED_TO_WINDOWS_VAULT=True")


def existing_access_valid(client: httpx.Client) -> bool:
    access = cred_read(ACCESS_TARGET)
    if not access:
        return False
    response = client.get(f"{API_BASE}/users/me", headers={"Authorization": f"Bearer {access}", "Accept": "application/json"})
    return response.status_code == 200


def refresh_access(client: httpx.Client, client_secret: str) -> bool:
    refresh = cred_read(REFRESH_TARGET)
    if not refresh:
        return False
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": APP_ID,
            "client_secret": client_secret,
            "refresh_token": refresh,
        },
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        return False
    payload = response.json()
    if not isinstance(payload, dict):
        return False
    validate_and_store_token(payload, client)
    print("OAUTH_REFRESH_USED=True")
    return True


class CallbackState:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    event = threading.Event()


def interactive_authorize(client: httpx.Client, client_secret: str, redirect_uri: str) -> None:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    expected_state = secrets.token_urlsafe(32)
    parsed_redirect = urlsplit(redirect_uri)
    callback_path = parsed_redirect.path or "/"
    state = CallbackState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path != callback_path:
                self.send_response(404)
                self.end_headers()
                return
            state.state = (query.get("state") or [None])[0]
            state.code = (query.get("code") or [None])[0]
            state.error = (query.get("error") or [None])[0]
            ok = bool(state.code and state.state == expected_state and not state.error)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("Autorizacao recebida. Pode fechar esta janela." if ok else "Autorizacao rejeitada.").encode("utf-8"))
            state.event.set()

    server = ThreadingHTTPServer((CALLBACK_HOST, CALLBACK_PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        auth = AUTH_URL + "?" + urlencode(
            {
                "response_type": "code",
                "client_id": APP_ID,
                "redirect_uri": redirect_uri,
                "state": expected_state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        print("OAUTH_BROWSER_AUTHORIZATION_REQUIRED=True")
        webbrowser.open(auth, new=1, autoraise=True)
        if not state.event.wait(timeout=300):
            raise RuntimeError("oauth_callback_timeout")
        if state.error:
            raise RuntimeError("oauth_authorization_rejected")
        if state.state != expected_state or not state.code:
            raise RuntimeError("oauth_state_or_code_invalid")
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": APP_ID,
                "client_secret": client_secret,
                "code": state.code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"oauth_exchange_http_{response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("oauth_exchange_invalid_payload")
        validate_and_store_token(payload, client)
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-interactive", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("windows_required")
    if os.getenv("MI_ML_APP_ID", APP_ID) != APP_ID:
        raise RuntimeError("application_id_mismatch")
    redirect_uri = os.getenv("MI_ML_REDIRECT_URI", "").strip()
    if not redirect_uri or urlsplit(redirect_uri).scheme.lower() != "https":
        raise RuntimeError("MI_ML_REDIRECT_URI_https_required")
    client_secret = cred_read(CLIENT_SECRET_TARGET)
    if not client_secret:
        raise RuntimeError("client_secret_missing_from_windows_vault")
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        if not args.force_interactive and existing_access_valid(client):
            print("OAUTH_EXISTING_ACCESS_VALID=True")
            return 0
        if not args.force_interactive and refresh_access(client, client_secret):
            return 0
        interactive_authorize(client, client_secret, redirect_uri)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
