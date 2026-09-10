# run_training.ps1 — overnight detector training with automatic resume.
#
# A transient CUDA fault, a driver reset, or a laptop hiccup should not cost the
# rest of the night. Ultralytics writes weights/last.pt every epoch, so this
# wrapper simply restarts and resumes from it, losing at most one epoch.
#
# Usage:
#   .\scripts\run_training.ps1                 # 48 epochs (the default)
#   .\scripts\run_training.ps1 -Epochs 60
#   .\scripts\run_training.ps1 -Epochs 60 -Workers 0    # page-file error 1455

param(
    [int]$Epochs = 50,
    [int]$Batch = 0,      # 0 = let train_yolo.py choose (its default is 4)
    [int]$Imgsz = 640,
    [int]$Workers = 2,
    [int]$MaxRetries = 20,
    [int]$RetryDelaySeconds = 30,
    [switch]$Resume    # continue an existing run rather than starting a new one
)

$ErrorActionPreference = "Continue"
$python = ".\venv\Scripts\python.exe"
$last = "outputs/training/ibvap_coarse/weights/last.pt"

if (-not (Test-Path $python)) {
    Write-Host "venv python not found at $python - run from the backend/ directory."
    exit 1
}

# A leftover checkpoint from a DIFFERENT run (a --benchmark, or a run with a
# different --epochs) would be resumed and declared finished immediately. Make
# the operator confirm rather than silently doing nothing.
if ((Test-Path $last) -and -not $Resume) {
    Write-Host "Found an existing checkpoint: $last"
    Write-Host "  Resuming it continues THAT run with ITS epoch count, not -Epochs $Epochs."
    Write-Host "  * to continue it:      .\scripts\run_training.ps1 -Resume"
    Write-Host "  * to start fresh:      Remove-Item -Recurse -Force outputs/training/ibvap_coarse"
    exit 2
}

for ($i = 1; $i -le $MaxRetries; $i++) {
    if (Test-Path $last) {
        Write-Host "=== attempt $i/$MaxRetries : resuming from $last ==="
        & $python scripts/train_yolo.py --resume --model $last
    }
    else {
        Write-Host "=== attempt $i/$MaxRetries : fresh start, $Epochs epochs ==="
        # Only override batch when explicitly asked. Hardcoding 8 here silently
        # contradicted train_yolo.py's own default of 4 and changed the run
        # behind the operator's back - visible only in the iteration count.
        if ($Batch -gt 0) {
            & $python scripts/train_yolo.py --epochs $Epochs --batch $Batch `
                --imgsz $Imgsz --workers $Workers
        }
        else {
            & $python scripts/train_yolo.py --epochs $Epochs `
                --imgsz $Imgsz --workers $Workers
        }
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host "=== training finished cleanly ==="
        Write-Host "    best: outputs/training/ibvap_coarse/weights/best.pt"
        Write-Host "    next: $python -m ml.eval_detector --weights outputs/training/ibvap_coarse/weights/best.pt"
        exit 0
    }

    Write-Host "=== exited with code $LASTEXITCODE ; retrying in ${RetryDelaySeconds}s ==="
    Start-Sleep -Seconds $RetryDelaySeconds
}

Write-Host "=== gave up after $MaxRetries attempts ==="
Write-Host "    Something is failing consistently, not transiently. Check the last"
Write-Host "    traceback above; common causes are CUDA OOM (lower --batch to 6 or 4)"
Write-Host "    and the Windows page-file error 1455 (add -Workers 0)."
exit 1
