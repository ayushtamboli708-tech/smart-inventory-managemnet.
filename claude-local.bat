@echo off
set ANTHROPIC_BASE_URL=http://localhost:1234
set ANTHROPIC_AUTH_TOKEN=lmstudio
set CLAUDE_CODE_ATTRIBUTION_HEADER=0
"%USERPROFILE%\.local\bin\claude.exe" %*
