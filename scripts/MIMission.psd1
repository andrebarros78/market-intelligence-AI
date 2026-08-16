@{
    RootModule = 'MIMission.psm1'
    ModuleVersion = '1.1.2'
    GUID = '6d8f4b32-2018-4f01-a347-7d0f2ae32ea5'
    Author = 'Market Intelligence AI'
    CompanyName = 'Private'
    Copyright = 'Private'
    Description = 'Local authenticated client for Sovereign Mission Protocol and conversational intelligence.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @(
        'Invoke-MIMission','Invoke-MIFollowUp','Get-MIMission','Get-MIReport','Get-MIHealth',
        'Get-MIBrief','Get-MIInbox','Get-MIContext','Get-MIEvidence','Get-MIThread','Get-MITimeline','Read-MIInboxItem'
    )
    CmdletsToExport = @()
    VariablesToExport = @()
    AliasesToExport = @()
}
