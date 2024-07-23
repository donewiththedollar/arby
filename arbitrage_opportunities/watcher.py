import aiohttp
import asyncio
import time
from collections import deque

BINANCE_ENDPOINT = "https://fapi.binance.com/fapi/v1/ticker/price"
BYBIT_ENDPOINT = "https://api.bybit.com/v2/public/tickers"

HISTORY_SIZE = 5

async def get_binance_price(session, symbol):
    params = {'symbol': symbol}
    async with session.get(BINANCE_ENDPOINT, params=params) as response:
        data = await response.json()
        return float(data['price'])

async def get_bybit_price(session, symbol):
    params = {'symbol': symbol}
    async with session.get(BYBIT_ENDPOINT, params=params) as response:
        data = await response.json()
        if data['ret_code'] == 0:
            for item in data['result']:
                if item['symbol'] == symbol:
                    return float(item['last_price'])
    return None

async def fetch_prices(symbol):
    async with aiohttp.ClientSession() as session:
        binance_price, bybit_price = await asyncio.gather(
            get_binance_price(session, symbol),
            get_bybit_price(session, symbol)
        )
    return binance_price, bybit_price

def determine_leader(binance_history, bybit_history):
    if len(binance_history) < HISTORY_SIZE or len(bybit_history) < HISTORY_SIZE:
        return "Undetermined"

    binance_net_change = binance_history[-1] - binance_history[0]
    bybit_net_change = bybit_history[-1] - bybit_history[0]

    if binance_net_change > bybit_net_change:
        return "Binance"
    elif bybit_net_change > binance_net_change:
        return "Bybit"
    else:
        return "Undetermined"

def main():
    symbol = input("Enter the symbol (e.g., BTCUSDT): ")

    binance_history = deque(maxlen=HISTORY_SIZE)
    bybit_history = deque(maxlen=HISTORY_SIZE)

    binance_lead_count = 0
    bybit_lead_count = 0
    total_checks = 0

    while True:
        binance_price, bybit_price = asyncio.run(fetch_prices(symbol))

        binance_history.append(binance_price)
        bybit_history.append(bybit_price)

        difference_percentage = ((binance_price - bybit_price) / bybit_price) * 100
        leader = determine_leader(binance_history, bybit_history)

        if leader == "Binance":
            binance_lead_count += 1
        elif leader == "Bybit":
            bybit_lead_count += 1

        total_checks += 1

        binance_lead_percentage = (binance_lead_count / total_checks) * 100
        bybit_lead_percentage = (bybit_lead_count / total_checks) * 100

        print(f"Binance: {binance_price} | Bybit: {bybit_price} | Difference: {difference_percentage:.2f}% | Leader: {leader} | Bybit Leading: {bybit_lead_percentage:.2f}% | Binance Leading: {binance_lead_percentage:.2f}%")
        time.sleep(0.2)  # Sleep for 0.2 seconds to print approximately 5 times a second

if __name__ == "__main__":
    main()