$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\data\pdfs')).Path
$manifestPath = Join-Path $PSScriptRoot 'word_to_pdf_manifest.json'
$items = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json

foreach ($item in $items) {
    $source = [System.IO.Path]::GetFullPath((Join-Path $root $item.source))
    $destination = [System.IO.Path]::GetFullPath((Join-Path $root $item.destination))

    if (-not $source.StartsWith($root)) {
        throw "Source outside workspace: $source"
    }
    if (-not $destination.StartsWith($root)) {
        throw "Destination outside workspace: $destination"
    }
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Host "SKIP missing: $($item.source)"
        continue
    }

    $destinationDir = Split-Path $destination -Parent
    New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null

    $word = $null
    $document = $null
    try {
        try {
            $word = New-Object -ComObject Word.Application
            $word.Visible = $false
            $word.DisplayAlerts = 0
            $word.AutomationSecurity = 3
            $document = $word.Documents.Open($source, $false, $true)
            $document.ExportAsFixedFormat($destination, 17)
        }
        finally {
            if ($document) {
                $document.Close($false)
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
            }
            if ($word) {
                $word.Quit()
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
            }
        }

        if (-not (Test-Path -LiteralPath $destination)) {
            throw "Export failed, no output file: $source"
        }
        if ((Get-Item -LiteralPath $destination).Length -eq 0) {
            throw "Export failed, empty output file: $source"
        }

        Remove-Item -LiteralPath $source -Force
        Write-Host "OK: $($item.source) -> $($item.destination)"
    }
    catch {
        Write-Host "FAILED: $($item.source) - $($_.Exception.Message)"
    }
}

Write-Host "Done"
