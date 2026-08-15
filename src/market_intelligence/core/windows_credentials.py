from __future__ import annotations
import ctypes
from ctypes import wintypes
CRED_TYPE_GENERIC=1
class _CredentialW(ctypes.Structure):
    _fields_=[("Flags",wintypes.DWORD),("Type",wintypes.DWORD),("TargetName",wintypes.LPWSTR),("Comment",wintypes.LPWSTR),("LastWritten",wintypes.FILETIME),("CredentialBlobSize",wintypes.DWORD),("CredentialBlob",ctypes.POINTER(ctypes.c_ubyte)),("Persist",wintypes.DWORD),("AttributeCount",wintypes.DWORD),("Attributes",ctypes.c_void_p),("TargetAlias",wintypes.LPWSTR),("UserName",wintypes.LPWSTR)]
def read_generic_credential(target:str)->str|None:
    adv=ctypes.WinDLL("Advapi32.dll"); read=adv.CredReadW; read.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.c_void_p)]; read.restype=wintypes.BOOL; free=adv.CredFree; free.argtypes=[ctypes.c_void_p]; ptr=ctypes.c_void_p()
    if not read(target,CRED_TYPE_GENERIC,0,ctypes.byref(ptr)):return None
    try:
        c=ctypes.cast(ptr,ctypes.POINTER(_CredentialW)).contents; size=int(c.CredentialBlobSize)
        if not c.CredentialBlob or size<=0:return None
        raw=ctypes.string_at(c.CredentialBlob,size)
        try:return raw.decode("utf-16-le")
        except UnicodeDecodeError:return raw.decode("utf-8")
    finally:free(ptr)
def write_generic_credential(target:str,secret:str,username:str="market-intelligence-ai")->None:
    if not target or not secret:raise ValueError("credential_target_and_secret_required")
    adv=ctypes.WinDLL("Advapi32.dll"); write=adv.CredWriteW; write.argtypes=[ctypes.POINTER(_CredentialW),wintypes.DWORD]; write.restype=wintypes.BOOL; raw=secret.encode("utf-16-le"); buf=ctypes.create_string_buffer(raw); c=_CredentialW(); c.Type=CRED_TYPE_GENERIC; c.TargetName=target; c.CredentialBlobSize=len(raw); c.CredentialBlob=ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)); c.Persist=2; c.UserName=username
    if not write(ctypes.byref(c),0):raise OSError("credential_write_failed")
