"""Example: LangChain ReAct agent using agentfetch tools.
Install: pip install agentfetch[langchain]
"""

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from agentfetch.integrations.langchain.tools import AgentFetchTools

llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = AgentFetchTools

prompt = PromptTemplate.from_template(
    "You are a research assistant. Use the tools to gather information.\n\n"
    "Question: {input}\n\n"
    "Thought: {agent_scratchpad}"
)

agent = create_react_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

result = agent_executor.invoke(
    {"input": "Research the latest developments in AI agents and summarize findings."}
)
print(result["output"])
