# AI-Powered eLearning Course Generator

## Project requirements

- Use Python 3.12, FastAPI for HTTP endpoints, and Pydantic v2 for request, response, and course models.
- Use the official Google Gen AI SDK with a configurable Gemini model available on the free tier. Read `GEMINI_API_KEY` and `GEMINI_MODEL` from the environment. Keep real credentials in an ignored local `.env` file or the process environment.
- Use PyMuPDF to extract text from PDFs and the official MCP Python SDK to expose course-generation tools. HTTP endpoints and MCP tools should call the same service functions.
- Validate generated course data with Pydantic before returning it. Handle invalid input, unreadable PDFs, and Gemini errors with clear messages. Keep API keys and uploaded document contents out of logs.
- Implement one working increment at a time. Show changes and get explicit approval before committing.

## Proposed layout

```text
app/
  main.py           # FastAPI app and initial health endpoint
  config.py         # Environment configuration
  schemas.py        # Pydantic models for requests and course output
  services/
    gemini.py       # Gemini client and structured generation
    pdf.py          # PDF text extraction
  mcp_server.py     # MCP tool entry point
tests/              # Tests for validation and service behavior
```

Add package directories and modules as the corresponding features are implemented.

## Coding conventions

- Follow PEP 8. Use descriptive names, type hints at function boundaries, and small functions with one clear purpose.
- Keep route and MCP handlers thin. Put shared logic in services and use Pydantic models at input and output boundaries.
- Keep dependencies explicit. Mock Gemini in automated tests so they run without credentials or API quota. Use small, non-sensitive PDF fixtures.
- Use a local `.venv` and run pip as `python -m pip`. Keep credentials, local environments, caches, and uploaded or generated files out of Git.
