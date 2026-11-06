$env:ANTHROPIC_BASE_URL = "http://localhost:1234"
$env:ANTHROPIC_AUTH_TOKEN = "lmstudio"
$env:CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
& "$env:USERPROFILE\.local\bin\claude.exe" @args
