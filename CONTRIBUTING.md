# Contributing to agentfetch

## Development setup

```bash
git clone https://github.com/[YOUR_USERNAME]/agentfetch
cd agentfetch
pip install -e ".[all]"
playwright install chromium
```

## Running tests

```bash
pytest tests/ -v
```

## Code style

- Type hints required for all public functions
- Pydantic models for all data exchange
- Async-first (except where sync is unavoidable)
- Never raise exceptions to callers — use error fields on models
- All extraction goes through the chain in `extractor.py`

## Pull request process

1. Open an issue describing the change
2. Fork the repo and create a branch
3. Add tests for any new functionality
4. Ensure all tests pass
5. Update relevant documentation

## Project structure

```
agentfetch/
├── packages/
│   ├── core/          # Router, extractor, sanitizer, stopper, schema
│   ├── integrations/  # LangChain, LlamaIndex, CrewAI, OpenAI
│   ├── mcp_server/    # MCP stdio and SSE transports
│   └── api/            # FastAPI REST server
├── tests/
└── examples/
```

Core package has zero framework dependencies. Integrations are optional installs.
