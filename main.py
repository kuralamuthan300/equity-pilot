import yfinance
from yfinance import EquityQuery


def main():
    search_info = yfinance.Search("NATCO",max_results=10)
    # for i in search_info.quotes:
    #     print("\n################################")
    #     print(i)
    ticket_result = yfinance.Ticker(search_info.quotes[1]['symbol'])
    ticket_info = ticket_result.info
    ticket_balance_sheet = ticket_result.get_balance_sheet(as_dict=True, pretty=False, freq='yearly')
    ticket_cashflow = ticket_result.get_cashflow(as_dict=True, pretty=False, freq='yearly')
    ticket_income_statement = ticket_result.get_income_stmt(as_dict=True, pretty=True, freq='quarterly')
    ticket_eps_revisions = ticket_result.get_eps_revisions(as_dict=True)

    news_of_company = ticket_result.get_news(count=10,tab='news')

    # print(ticket_info)
    # print(ticket_balance_sheet)
    # for i in news_of_company:
    #     print(i['content']['title'])
    #     print(i['content']['summary'])
    #     print(i['content']['provider']['displayName'])
    #     print(i['content']['canonicalUrl']['url'])
    #     print(i['content']['pubDate'])
    #     print(i['content']['clickThroughUrl']['url'])
    #     print("\n################################")
    print(ticket_result.get_funds_data())

if __name__ == "__main__":
    main()
