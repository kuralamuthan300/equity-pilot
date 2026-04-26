import yfinance as yf
from fastmcp import FastMCP

mcp = FastMCP("equity-pilot")
class MCPserver():
    def __init__(self):
        pass

    def search_company(self,company_name:str,max_results:int=10)->list:
        search = yf.Search(company_name,max_results=max_results)
        return search.quotes
    
    def get_company_info(self,symbol:str)->dict:
        return yf.Ticker(symbol).info
    
    def get_company_financials(self,symbol:str)->dict:
        ticket_result = yf.Ticker(symbol)
        ticket_balance_sheet = ticket_result.get_balance_sheet(as_dict=True, pretty=False, freq='yearly')
        ticket_cashflow = ticket_result.get_cashflow(as_dict=True, pretty=False, freq='yearly')
        ticket_income_statement = ticket_result.get_income_stmt(as_dict=True, pretty=False, freq='yearly')
        return {"balance_sheet":ticket_balance_sheet,"cashflow":ticket_cashflow,"income_statement":ticket_income_statement}
    
