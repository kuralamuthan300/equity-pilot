import ollama
import asyncio
import sys
import os
import json
import re

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config.config import API_KEY
from config.config import system_prompt as cf_system_prompt

# Path to the MCP server script (relative to project root)
MCP_SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server", "mcp_server.py")
MCP_SERVER_CWD    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server")


def _describe_tools(tools) -> str:
    """Format MCP tool list into a human-readable string for the system prompt."""
    lines = []
    for t in tools:
        props = (t.inputSchema or {}).get("properties", {})
        params = ", ".join(f"{n}: {p.get('type', 'any')}" for n, p in props.items()) or "no params"
        lines.append(f"- {t.name}({params}): {t.description or 'No description'}")
    return "\n".join(lines)


class Agent:

    def __init__(self, model_name: str = 'gemma4:31b-cloud'):
        self.client = ollama.Client(
            host='https://ollama.com',
            headers={'Authorization': f'Bearer {API_KEY}'}
        )
        self.model_name = model_name
        self.query_history = []
        self.response_history = []
        self.conversation_summary = ""

        # MCP state
        self.mcp_session = None
        self.tools = []
        self.tools_desc = ""
        self._read_write_cm = None
        self._session_cm = None

    # -------------------------------------------------------------------------
    # MCP Connection
    # -------------------------------------------------------------------------

    async def connect_mcp(self, server_script: str = MCP_SERVER_SCRIPT, cwd: str = MCP_SERVER_CWD):
        """Start the MCP server subprocess and discover its tools."""
        server_params = StdioServerParameters(
            command=sys.executable,      # Use the same Python that's running this script
            args=[server_script],
            cwd=cwd,
        )
        self._read_write_cm = stdio_client(server_params)
        read, write = await self._read_write_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self.mcp_session = await self._session_cm.__aenter__()
        await self.mcp_session.initialize()

        self.tools = (await self.mcp_session.list_tools()).tools
        self.tools_desc = _describe_tools(self.tools)
        print(f"✓ Connected to MCP server — {len(self.tools)} tools loaded:")
        for t in self.tools:
            print(f"   • {t.name}")

    async def disconnect_mcp(self):
        """Clean up the MCP session and subprocess."""
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._read_write_cm:
            await self._read_write_cm.__aexit__(None, None, None)

    # -------------------------------------------------------------------------
    # Prompt Construction
    # -------------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build the full system prompt, injecting tools if connected to MCP."""
        tools_section = ""
        if self.tools_desc:
            tools_section = f"""

### Available Tools:
{self.tools_desc}

### Tool Usage Protocol:
You may call tools to gather information before giving a final answer.

To call a tool, respond with JSON in this exact format:
{{"action": "tool_call", "tool": "<tool_name>", "args": {{<key: value pairs>}}, "conversation_summary": "<updated summary>"}}

When you have enough information and are ready to answer the user:
{{"action": "final_answer", "response": "<your complete response>", "conversation_summary": "<updated summary>"}}

Rules:
- Only call tools that are listed above.
- You will receive the tool result and can then call another tool or give a final_answer.
- Always end with a "final_answer" action.
"""
        return cf_system_prompt + tools_section

    def _build_messages(self, query: str) -> list:
        """Build the messages list, including full interaction history."""
        full_history = ""
        if self.query_history:
            full_history = "\n\n### Full Interaction History:\n"
            for q, r in zip(self.query_history, self.response_history):
                full_history += f"User: {q}\nAgent: {r}\n---\n"

        return [
            {'role': 'system', 'content': self._build_system_prompt() + full_history},
            {'role': 'user', 'content': query},
        ]

    # -------------------------------------------------------------------------
    # LLM Call + JSON Processing
    # -------------------------------------------------------------------------

    def _llm_call(self, messages: list) -> str:
        """Blocking synchronous LLM call via Ollama."""
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                stream=False
            )
            return response.message.content
        except Exception as e:
            return str(e)

    def _process_json(self, raw_res: str) -> dict:
        """Extract and parse a JSON object from the raw LLM response."""
        # Find the first '{' to start decoding from
        start_idx = raw_res.find('{')
        if start_idx == -1:
            print(f"JSON Processing Error: No '{{' found in response.\nRaw response: {raw_res}")
            return {
                "action": "final_answer",
                "response": "I'm sorry, I encountered an error processing the response. Please try again.",
                "conversation_summary": self.conversation_summary
            }

        try:
            # Use raw_decode to ignore trailing garbage after the first valid JSON object
            decoder = json.JSONDecoder()
            res_dict, _ = decoder.raw_decode(raw_res[start_idx:])
            
            if "action" not in res_dict:
                raise ValueError("Missing required key 'action'")
            return res_dict
        except (json.JSONDecodeError, ValueError) as e:
            print(f"JSON Processing Error: {e}\nRaw response: {raw_res}")
            return {
                "action": "final_answer",
                "response": "I'm sorry, I encountered an error processing the response. Please try again.",
                "conversation_summary": self.conversation_summary
            }


    # -------------------------------------------------------------------------
    # Agentic Loop
    # -------------------------------------------------------------------------

    async def ask_agent(self, query: str, max_iterations: int = 6) -> str:
        """
        Run the agentic loop:
          LLM decides → (tool_call → observe → repeat) | final_answer
        """
        loop = asyncio.get_running_loop()
        messages = self._build_messages(query)

        for iteration in range(1, max_iterations + 1):
            print(f"\n[Iteration {iteration}] Calling LLM...")

            # Run the blocking LLM call in a thread pool
            raw_res = await loop.run_in_executor(None, self._llm_call, messages)
            res_dict = self._process_json(raw_res)
            action = res_dict.get("action", "final_answer")

            # Always update the running conversation summary
            self.conversation_summary = res_dict.get("conversation_summary", self.conversation_summary)

            if action == "tool_call" and self.mcp_session:
                tool_name = res_dict.get("tool", "")
                tool_args = res_dict.get("args", {})
                print(f"→ Tool call: {tool_name}({tool_args})")

                try:
                    result = await self.mcp_session.call_tool(tool_name, arguments=tool_args)
                    tool_output = (
                        result.content[0].text
                        if result.content and hasattr(result.content[0], "text")
                        else str(result)
                    )
                except Exception as e:
                    tool_output = f"ERROR calling tool '{tool_name}': {e}"

                print(f"← Tool result: {tool_output[:200]}{'...' if len(str(tool_output)) > 200 else ''}")

                # Append tool call + result to messages for the next iteration
                messages.append({'role': 'assistant', 'content': raw_res})
                messages.append({'role': 'user', 'content': f"Tool '{tool_name}' returned:\n{tool_output}"})

            elif action == "tool_call" and not self.mcp_session:
                print("Warning: LLM requested a tool call but no MCP session is active.")
                messages.append({'role': 'assistant', 'content': raw_res})
                messages.append({'role': 'user', 'content': "No MCP tools available. Please answer using your existing knowledge."})

            else:
                # Final answer reached
                response_text = res_dict.get("response", raw_res)
                self.query_history.append(query)
                self.response_history.append(response_text)
                return response_text

        # Fallback if max iterations exhausted
        fallback = "I reached the maximum number of reasoning steps. Please rephrase your query."
        self.query_history.append(query)
        self.response_history.append(fallback)
        return fallback


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------

if __name__ == '__main__':
    async def main():
        agent = Agent()

        # Connect to MCP server
        try:
            await agent.connect_mcp()
        except Exception as e:
            print(f"Warning: Could not connect to MCP server: {e}")
            print("Running without MCP tools.\n")

        iteration = 0
        MAX_ITERATIONS = 100
        while iteration < MAX_ITERATIONS:
            user_query = input("\nEnter your query (type quit to exit): ")
            if user_query.lower() == 'quit':
                break
            res = await agent.ask_agent(user_query)
            print(f"\nAgent: {res}")
            iteration += 1

        print("\n\nConversation Summary:", agent.conversation_summary)

        # Clean up MCP connection
        await agent.disconnect_mcp()

    asyncio.run(main())