from mcp.server.fastmcp import FastMCP
import asyncio
from orchestrator.agent import Agent 

# 1. Initialize your server
mcp = FastMCP("orchestrator_mcp_server")

# 2. Initialize your class instance
agent = Agent()

# 3. Register the instance method as a tool
@mcp.tool()
async def call_llm(prompt: str) -> str:
    """Sends a prompt to the internal LLM service."""
    try:
        await agent.connect_mcp()
    except Exception as e:
        print(f"Warning: Could not connect to MCP server: {e}")
        print("Running without MCP tools.\n")
    return await agent.ask(prompt)

if __name__ == "__main__":
    mcp.run()