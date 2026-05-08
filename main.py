import yfinance
from yfinance import EquityQuery


def main():
    query = EquityQuery("NATCO", max_results=10)
    print(query.fund_data)

if __name__ == "__main__":
    main()
