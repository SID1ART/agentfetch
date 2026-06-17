#!/bin/bash
# Example: Using agentfetch via REST API.
# Install: pip install agentfetch && agentfetch serve

# Start the server:
#   agentfetch serve

# 1. Scrape a webpage
curl -X POST http://localhost:8080/agent_scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "engine": "auto"}'

# 2. Search the web
curl -X POST http://localhost:8080/agent_search \
  -H "Content-Type: application/json" \
  -d '{"query": "AI agent frameworks", "max_results": 3}'

# 3. Health check
curl http://localhost:8080/health
