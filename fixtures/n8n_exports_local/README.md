# Local n8n exports (redacted)

These files are **read-only snapshots** of workflows stored in the local
n8n SQLite DB (`%USERPROFILE%\.n8n\database.sqlite`). Secrets and credential
IDs are redacted.

## Refresh export

```powershell
python scripts/_inspect_n8n_local.py
python scripts/_audit_mega_workflow.py
```

## Import into another n8n

Prefer exporting from the n8n UI:

1. Open Mega_Workflow  
2. `…` → Download  
3. Store the JSON outside git if it contains credentials, or scrub before commit  

Do **not** treat this folder as the live source of truth for production
`https://n8n.bhuvisx.com`.
