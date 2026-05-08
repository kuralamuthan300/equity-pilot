from fastmcp import FastMCP
from yscreener_tools import register_all_screener_mcp_tools
from file_folder_management_tools import register_all_file_access_tools

if __name__ == "__main__":
    # Initialize MCP
    mcp = FastMCP('equity-pilot')

    # Register all screener tools defined in ALL_TOOLS
    register_all_screener_mcp_tools(mcp)
    register_all_file_access_tools(mcp)
    
    # Start the MCP server
    mcp.run()