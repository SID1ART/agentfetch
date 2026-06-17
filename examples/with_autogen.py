"""Example: AutoGen ConversableAgent using agentfetch via OpenAI tool spec.
Install: pip install pyautogen agentfetch
"""

import autogen
from agentfetch.integrations.openai.tools import get_tools, handle_tool_call

config_list = [{"model": "gpt-4o", "api_key": "YOUR_API_KEY"}]

llm_config = {
    "config_list": config_list,
    "functions": get_tools(),
}

assistant = autogen.AssistantAgent(
    name="assistant",
    llm_config=llm_config,
    system_message="You use agentfetch tools to fetch web content.",
)

user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    code_execution_config=False,
    function_map={
        "agentfetch_scrape": lambda args: handle_tool_call("agentfetch_scrape", args),
        "agentfetch_search": lambda args: handle_tool_call("agentfetch_search", args),
        "agentfetch_crawl": lambda args: handle_tool_call("agentfetch_crawl", args),
    },
)

user_proxy.initiate_chat(
    assistant,
    message="Research the latest developments in AI and provide a summary.",
    max_turns=5,
)
