# JARVIS Browser Research Agent

This companion service runs on your Windows laptop. GitHub Pages cannot control a local browser on its own, so this local Python service is required.

## Start

1. Install Python 3.10 or newer.
2. Double-click START-RESEARCH-AGENT.bat.
3. Keep its terminal window open.
4. Open the JARVIS dashboard and run Research Mode.
5. On the first browser launch, handle Google consent/login pages manually. This agent does not bypass CAPTCHA, authentication, or access controls.

## Optional local AI synthesis (no AI API key)

Install Ollama from https://ollama.com/download, then run:

    ollama pull qwen2.5:3b

The agent tries qwen2.5:3b at http://127.0.0.1:11434. If Ollama is not running, it compiles the page text and labels it as a compilation rather than AI synthesis.

## API

- GET http://127.0.0.1:8765/health
- POST http://127.0.0.1:8765/research with {"query":"...","duration_seconds":10}
- GET http://127.0.0.1:8765/jobs/JOB_ID

The timer controls web collection time, not the total time required for AI report generation.

## Safety and limitations

- Browser automation opens a visible Chromium session and reads pages available without defeating access controls.
- Search pages may change, require consent, rate-limit, or block automation. The agent does not bypass CAPTCHA or sign-in gates.
- Search results can be inaccurate; review important claims.
- Local AI synthesis is optional and requires no Gemini/OpenAI API key.
