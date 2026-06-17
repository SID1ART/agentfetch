"""Example: Custom agent loop using agentfetch as a tool.
Install: pip install agentfetch
"""

import json
import asyncio
from agentfetch.integrations.openai.tools import get_tools, handle_tool_call
from openai import OpenAI

SYSTEM_PROMPT = """You are a research agent with access to web tools.
Use them to answer the user's question. When you need to use a tool,
respond with a JSON block:

{"tool": "tool_name", "args": {...}}

Then wait for the result and continue."""


def run_agent(user_message: str, max_turns: int = 5):
    client = OpenAI()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    tools_desc = json.dumps(get_tools(), indent=2)
    print(f"Available tools:\n{tools_desc}\n")

    for turn in range(max_turns):
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0,
        )
        content = resp.choices[0].message.content

        if not content:
            break

        print(f"\n--- Turn {turn + 1} ---\n{content}\n")

        try:
            tool_call = json.loads(content)
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {})

            if tool_name:
                result = handle_tool_call(tool_name, tool_args)
                print(f"Tool result:\n{result[:500]}...\n")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Tool result: {result}"})
                continue
        except (json.JSONDecodeError, KeyError):
            pass

        break

    return content


if __name__ == "__main__":
    result = run_agent("Research the latest developments in AI agents.")
    print(f"\nFinal answer:\n{result}")
