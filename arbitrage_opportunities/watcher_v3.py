import aiohttp
import asyncio
import time
from collections import deque
from tabulate import tabulate

BINANCE_ENDPOINT = "https://api.binance.com/api/v3/ticker/price"
BYBIT_ENDPOINT = "https://api.bybit.com/v5/market/tickers"
COINBASE_ENDPOINT = "https://api.coinbase.com/v2/prices/{symbol}/spot"

HISTORY_SIZE = 5
ARBITRAGE_THRESHOLD = 1.0  # Arbitrage opportunity threshold in percentage

def convert_symbol(symbol, exchange):
    if exchange == "binance" or exchange == "bybit":
        return symbol.replace("-", "").replace("USD", "USDT")
    return symbol

async def get_binance_price(session, symbol):
    params = {'symbol': convert_symbol(symbol, 'binance')}
    async with session.get(BINANCE_ENDPOINT, params=params) as response:
        data = await response.json()
        if 'price' in data:
            return float(data['price'])
        else:
            print(f"Error fetching Binance price: {data}")
            return None

async def get_bybit_price(session, category, symbol):
    params = {'category': category, 'symbol': convert_symbol(symbol, 'bybit')}
    async with session.get(BYBIT_ENDPOINT, params=params) as response:
        data = await response.json()
        if data['retCode'] == 0:
            for item in data['result']['list']:
                if item['symbol'] == convert_symbol(symbol, 'bybit'):
                    return float(item['lastPrice'])
        else:
            print(f"Error fetching Bybit price: {data}")
        return None

async def get_coinbase_price(session, symbol):
    async with session.get(COINBASE_ENDPOINT.format(symbol=symbol)) as response:
        data = await response.json()
        if 'data' in data and 'amount' in data['data']:
            return float(data['data']['amount'])
        else:
            print(f"Error fetching Coinbase price: {data}")
            return None

async def fetch_prices(symbol):
    async with aiohttp.ClientSession() as session:
        binance_price, bybit_price, coinbase_price = await asyncio.gather(
            get_binance_price(session, symbol),
            get_bybit_price(session, 'spot', symbol),
            get_coinbase_price(session, symbol)
        )
    return binance_price, bybit_price, coinbase_price

def determine_leader(binance_history, bybit_history, coinbase_history):
    if len(binance_history) < HISTORY_SIZE or len(bybit_history) < HISTORY_SIZE or len(coinbase_history) < HISTORY_SIZE:
        return "Undetermined"

    binance_net_change = binance_history[-1] - binance_history[0]
    bybit_net_change = bybit_history[-1] - bybit_history[0]
    coinbase_net_change = coinbase_history[-1] - coinbase_history[0]

    changes = {'Binance': binance_net_change, 'Bybit': bybit_net_change, 'Coinbase': coinbase_net_change}
    leader = max(changes, key=changes.get)

    if changes[leader] == 0:
        return "Undetermined"
    return leader

def log_arbitrage_opportunity(opportunity):
    with open("arbitrage_opportunities.log", "a") as log_file:
        log_file.write(opportunity + "\n")

def main():
    symbol = input("Enter the symbol (e.g., BTCUSDT for Binance/Bybit, BTC-USD for Coinbase): ")

    binance_history = deque(maxlen=HISTORY_SIZE)
    bybit_history = deque(maxlen=HISTORY_SIZE)
    coinbase_history = deque(maxlen=HISTORY_SIZE)

    binance_lead_count = 0
    bybit_lead_count = 0
    coinbase_lead_count = 0
    total_checks = 0

    while True:
        binance_price, bybit_price, coinbase_price = asyncio.run(fetch_prices(symbol))

        if binance_price is not None:
            binance_history.append(binance_price)
        if bybit_price is not None:
            bybit_history.append(bybit_price)
        if coinbase_price is not None:
            coinbase_history.append(coinbase_price)

        if binance_price is not None and bybit_price is not None and coinbase_price is not None:
            difference_percentage_binance_bybit = ((binance_price - bybit_price) / bybit_price) * 100
            difference_percentage_binance_coinbase = ((binance_price - coinbase_price) / coinbase_price) * 100
            difference_percentage_bybit_coinbase = ((bybit_price - coinbase_price) / coinbase_price) * 100

            leader = determine_leader(binance_history, bybit_history, coinbase_history)

            if leader == "Binance":
                binance_lead_count += 1
            elif leader == "Bybit":
                bybit_lead_count += 1
            elif leader == "Coinbase":
                coinbase_lead_count += 1

            total_checks += 1

            binance_lead_percentage = (binance_lead_count / total_checks) * 100
            bybit_lead_percentage = (bybit_lead_count / total_checks) * 100
            coinbase_lead_percentage = (coinbase_lead_count / total_checks) * 100

            arbitrage_opportunity = ""
            if abs(difference_percentage_binance_bybit) > ARBITRAGE_THRESHOLD:
                arbitrage_opportunity = f"Buy on {'Bybit' if difference_percentage_binance_bybit > 0 else 'Binance'} and sell on {'Binance' if difference_percentage_binance_bybit > 0 else 'Bybit'}"
                log_arbitrage_opportunity(arbitrage_opportunity)
            elif abs(difference_percentage_binance_coinbase) > ARBITRAGE_THRESHOLD:
                arbitrage_opportunity = f"Buy on {'Coinbase' if difference_percentage_binance_coinbase > 0 else 'Binance'} and sell on {'Binance' if difference_percentage_binance_coinbase > 0 else 'Coinbase'}"
                log_arbitrage_opportunity(arbitrage_opportunity)
            elif abs(difference_percentage_bybit_coinbase) > ARBITRAGE_THRESHOLD:
                arbitrage_opportunity = f"Buy on {'Coinbase' if difference_percentage_bybit_coinbase > 0 else 'Bybit'} and sell on {'Bybit' if difference_percentage_bybit_coinbase > 0 else 'Coinbase'}"
                log_arbitrage_opportunity(arbitrage_opportunity)

            table = [
                ["Exchange", "Price", "Difference %", "Leader %", "Arbitrage Opportunity"],
                ["Binance", binance_price, f"{difference_percentage_binance_bybit:.2f}% / {difference_percentage_binance_coinbase:.2f}%", f"{binance_lead_percentage:.2f}%", arbitrage_opportunity if "Binance" in arbitrage_opportunity else ""],
                ["Bybit", bybit_price, f"{difference_percentage_bybit_coinbase:.2f}% / {difference_percentage_binance_bybit:.2f}%", f"{bybit_lead_percentage:.2f}%", arbitrage_opportunity if "Bybit" in arbitrage_opportunity else ""],
                ["Coinbase", coinbase_price, f"{difference_percentage_bybit_coinbase:.2f}% / {difference_percentage_binance_coinbase:.2f}%", f"{coinbase_lead_percentage:.2f}%", arbitrage_opportunity if "Coinbase" in arbitrage_opportunity else ""]
            ]

            print("\nArbitrage opportunities by Tyler Simpson\n")
            print(tabulate(table, headers="firstrow", tablefmt="grid"))
        else:
            print(f"Could not retrieve prices for all exchanges. Skipping calculation.")

        time.sleep(0.2)  # Sleep for 0.2 seconds to print approximately 5 times a second

if __name__ == "__main__":
    main()
