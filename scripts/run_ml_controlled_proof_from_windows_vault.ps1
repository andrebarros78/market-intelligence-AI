param(
    [switch]$ReplaceToken
)

$ErrorActionPreference = "Stop"
$Target = "MarketIntelligenceAI/MercadoLivre/ControlledWriteToken"
$Repo = Split-Path -Parent $PSScriptRoot

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class WinCred {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct CREDENTIAL {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    [DllImport("advapi32.dll", EntryPoint="CredWriteW", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool CredWrite(ref CREDENTIAL credential, UInt32 flags);

    [DllImport("advapi32.dll", EntryPoint="CredReadW", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credentialPtr);

    [DllImport("advapi32.dll", EntryPoint="CredFree", SetLastError=true)]
    public static extern void CredFree(IntPtr cred);

    public static void WriteGeneric(string target, string userName, string secret) {
        byte[] bytes = Encoding.Unicode.GetBytes(secret);
        IntPtr blob = Marshal.AllocHGlobal(bytes.Length);
        try {
            Marshal.Copy(bytes, 0, blob, bytes.Length);
            CREDENTIAL c = new CREDENTIAL();
            c.Type = 1; // CRED_TYPE_GENERIC
            c.TargetName = target;
            c.UserName = userName;
            c.CredentialBlobSize = (UInt32)bytes.Length;
            c.CredentialBlob = blob;
            c.Persist = 2; // CRED_PERSIST_LOCAL_MACHINE
            if (!CredWrite(ref c, 0)) {
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            }
        }
        finally {
            if (blob != IntPtr.Zero) {
                for (int i = 0; i < bytes.Length; i++) Marshal.WriteByte(blob, i, 0);
                Marshal.FreeHGlobal(blob);
            }
        }
    }

    public static string ReadGeneric(string target) {
        IntPtr ptr;
        if (!CredRead(target, 1, 0, out ptr)) return null;
        try {
            CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(ptr, typeof(CREDENTIAL));
            if (c.CredentialBlob == IntPtr.Zero || c.CredentialBlobSize == 0) return null;
            return Marshal.PtrToStringUni(c.CredentialBlob, (int)c.CredentialBlobSize / 2);
        }
        finally { CredFree(ptr); }
    }
}
'@

function Save-TokenToVault {
    $secure = Read-Host "Cole o ACCESS TOKEN valido do Mercado Livre (sera salvo no Cofre do Windows)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        if ([string]::IsNullOrWhiteSpace($plain)) { throw "Token vazio." }
        [WinCred]::WriteGeneric($Target, $env:USERNAME, $plain)
    }
    finally {
        if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        if ($plain) { $plain = $null }
    }
    Write-Host "TOKEN_SAVED_TO_WINDOWS_VAULT=True"
}

if ($ReplaceToken -or -not [WinCred]::ReadGeneric($Target)) {
    Save-TokenToVault
}

$token = [WinCred]::ReadGeneric($Target)
if ([string]::IsNullOrWhiteSpace($token)) { throw "Token ausente no Cofre do Windows." }

try {
    $env:MI_ML_TEMP_WRITE_TOKEN = $token
    $env:PYTHONPATH = "$Repo\src;$Repo"
    Set-Location $Repo
    python scripts/run_ml_controlled_pause_resume_windows.py
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:MI_ML_TEMP_WRITE_TOKEN -ErrorAction SilentlyContinue
    $token = $null
}
