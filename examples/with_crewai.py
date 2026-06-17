"""Example: CrewAI multi-agent crew using agentfetch tools.
Install: pip install agentfetch[crewai]
"""

from crewai import Agent, Task, Crew, Process
from agentfetch.integrations.crewai.tools import scrape_tool, search_tool, crawl_tool

researcher = Agent(
    role="Researcher",
    goal="Gather information from the web using agentfetch tools",
    backstory="Expert web researcher using agentfetch to collect data",
    tools=[scrape_tool, search_tool, crawl_tool],
    verbose=True,
)

writer = Agent(
    role="Writer",
    goal="Synthesize research into a clear summary",
    backstory="Expert at turning raw data into readable content",
    verbose=True,
)

research_task = Task(
    description="Research the topic of AI agent frameworks and their capabilities.",
    agent=researcher,
    expected_output="A collection of research notes from web searches.",
)

write_task = Task(
    description="Write a summary of the research findings.",
    agent=writer,
    expected_output="A well-organized summary of AI agent frameworks.",
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential,
)

result = crew.kickoff()
print(result)
