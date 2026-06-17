"""Example: LlamaIndex query engine using agentfetch as a tool.
Install: pip install agentfetch[llamaindex]
"""

from llama_index.core import VectorStoreIndex, Document
from llama_index.core.tools import QueryEngineTool
from llama_index.core.agent import ReActAgent
from llama_index.llms.openai import OpenAI
from agentfetch.integrations.llamaindex.tools import AgentFetchToolSpec

llm = OpenAI(model="gpt-4o", temperature=0)
tool_spec = AgentFetchToolSpec()
tools = tool_spec.to_tool_list()

agent = ReActAgent.from_tools(tools, llm=llm, verbose=True)

response = agent.query("Fetch https://example.com and summarize the content.")
print(response)
