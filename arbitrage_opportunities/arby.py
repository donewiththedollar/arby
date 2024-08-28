import aiohttp
import asyncio
import time
import json
from collections import deque
from datetime import datetime, timedelta
from tabulate import tabulate
from colorama import Fore, Style, init

init(autoreset=True)

BINANCE_ENDPOINT = "https://api.binance.com/api/v3/ticker/price"
BYBIT_ENDPOINT = "https://api.bybit.com/v5/market/tickers"
COINBASE_ENDPOINT = "https://api.coinbase.com/v2/prices/{symbol}/spot"

HISTORY_SIZE = 20
ARBITRAGE_THRESHOLD = 0.02  # Arbitrage opportunity threshold in percentage
TWAP_PERIOD = 60  # TWAP calculation period in seconds
TWAP_THRESHOLD = 0.01  # Threshold for detecting TWAP patterns

def read_config():
    with open('config.json', 'r') as file:
        config = json.load(file)
    return config

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
            print(f"{Fore.RED}Error fetching Binance price: {data}")
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
            print(f"{Fore.RED}Error fetching Bybit price: {data}")
        return None

async def get_coinbase_price(session, symbol):
    async with session.get(COINBASE_ENDPOINT.format(symbol=symbol)) as response:
        data = await response.json()
        if 'data' in data and 'amount' in data['data']:
            return float(data['data']['amount'])
        else:
            print(f"{Fore.RED}Error fetching Coinbase price: {data}")
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

def calculate_twap(prices, timestamps, period):
    end_time = timestamps[-1]
    start_time = end_time - timedelta(seconds=period)
    relevant_prices = [price for price, timestamp in zip(prices, timestamps) if timestamp >= start_time]

    if not relevant_prices:
        return None, None

    twap = sum(relevant_prices) / len(relevant_prices)
    direction = "Ask" if prices[-1] > twap else "Bid"
    return twap, direction

def detect_twap_pattern(prices, period, threshold):
    if len(prices) < period:
        return False

    recent_prices = prices[-period:]
    price_changes = [abs(recent_prices[i] - recent_prices[i - 1]) for i in range(1, len(recent_prices))]
    average_change = sum(price_changes) / len(price_changes)

    return average_change <= threshold

def estimate_twap_order_size(prices):
    if len(prices) < 2:
        return None

    price_changes = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
    average_change = sum(price_changes) / len(price_changes)
    estimated_order_size = average_change * len(prices)
    return estimated_order_size

def main():
    config = read_config()
    symbol = config.get("symbol", "BTCUSDT")
    print(f"{Fore.GREEN}Screening token: {Fore.YELLOW}{symbol}")

    binance_history = deque(maxlen=HISTORY_SIZE)
    bybit_history = deque(maxlen=HISTORY_SIZE)
    coinbase_history = deque(maxlen=HISTORY_SIZE)
    
    binance_timestamps = deque(maxlen=HISTORY_SIZE)
    bybit_timestamps = deque(maxlen=HISTORY_SIZE)
    coinbase_timestamps = deque(maxlen=HISTORY_SIZE)

    binance_lead_count = 0
    bybit_lead_count = 0
    coinbase_lead_count = 0
    total_checks = 0

    while True:
        binance_price, bybit_price, coinbase_price = asyncio.run(fetch_prices(symbol))
        current_time = datetime.now()

        if binance_price is not None:
            binance_history.append(binance_price)
            binance_timestamps.append(current_time)
        if bybit_price is not None:
            bybit_history.append(bybit_price)
            bybit_timestamps.append(current_time)
        if coinbase_price is not None:
            coinbase_history.append(coinbase_price)
            coinbase_timestamps.append(current_time)

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
                arbitrage_opportunity = f"{Style.BRIGHT}{Fore.RED}Buy on {'Bybit' if difference_percentage_binance_bybit > 0 else 'Binance'} and sell on {'Binance' if difference_percentage_binance_bybit > 0 else 'Bybit'}{Style.RESET_ALL}"
                log_arbitrage_opportunity(arbitrage_opportunity)
            elif abs(difference_percentage_binance_coinbase) > ARBITRAGE_THRESHOLD:
                arbitrage_opportunity = f"{Style.BRIGHT}{Fore.RED}Buy on {'Coinbase' if difference_percentage_binance_coinbase > 0 else 'Binance'} and sell on {'Binance' if difference_percentage_binance_coinbase > 0 else 'Coinbase'}{Style.RESET_ALL}"
                log_arbitrage_opportunity(arbitrage_opportunity)
            elif abs(difference_percentage_bybit_coinbase) > ARBITRAGE_THRESHOLD:
                arbitrage_opportunity = f"{Style.BRIGHT}{Fore.RED}Buy on {'Coinbase' if difference_percentage_bybit_coinbase > 0 else 'Bybit'} and sell on {'Bybit' if difference_percentage_bybit_coinbase > 0 else 'Coinbase'}{Style.RESET_ALL}"
                log_arbitrage_opportunity(arbitrage_opportunity)

            binance_twap, binance_twap_direction = calculate_twap(list(binance_history), list(binance_timestamps), TWAP_PERIOD)
            bybit_twap, bybit_twap_direction = calculate_twap(list(bybit_history), list(bybit_timestamps), TWAP_PERIOD)
            coinbase_twap, coinbase_twap_direction = calculate_twap(list(coinbase_history), list(coinbase_timestamps), TWAP_PERIOD)

            binance_twap_detected = detect_twap_pattern(list(binance_history), HISTORY_SIZE, TWAP_THRESHOLD)
            bybit_twap_detected = detect_twap_pattern(list(bybit_history), HISTORY_SIZE, TWAP_THRESHOLD)
            coinbase_twap_detected = detect_twap_pattern(list(coinbase_history), HISTORY_SIZE, TWAP_THRESHOLD)

            binance_twap_order_size = estimate_twap_order_size(list(binance_history))
            bybit_twap_order_size = estimate_twap_order_size(list(bybit_history))
            coinbase_twap_order_size = estimate_twap_order_size(list(coinbase_history))

            headers = [
                f"{Fore.BLUE}Exchange", 
                f"{Fore.BLUE}Price", 
                f"{Fore.BLUE}Difference %", 
                f"{Fore.BLUE}Leader %", 
                f"{Fore.BLUE}Arbitrage Opportunity",
                f"{Fore.BLUE}TWAP",
                f"{Fore.BLUE}TWAP Detected",
                f"{Fore.BLUE}TWAP Direction",
                f"{Fore.BLUE}Est. TWAP Order Size"
            ]
            
            table = [
                ["Binance", f"{Fore.GREEN}{binance_price}", f"{Fore.CYAN}{difference_percentage_binance_bybit:.2f}% / {difference_percentage_binance_coinbase:.2f}%", f"{Fore.MAGENTA}{binance_lead_percentage:.2f}%", arbitrage_opportunity if "Binance" in arbitrage_opportunity else "", f"{Fore.YELLOW}{binance_twap:.2f}" if binance_twap else "N/A", f"{Fore.RED}Yes" if binance_twap_detected else "No", f"{Fore.YELLOW}{binance_twap_direction}" if binance_twap_direction else "N/A", f"{Fore.YELLOW}{binance_twap_order_size:.2f}" if binance_twap_order_size else "N/A"],
                ["Bybit", f"{Fore.GREEN}{bybit_price}", f"{Fore.CYAN}{difference_percentage_bybit_coinbase:.2f}% / {difference_percentage_binance_bybit:.2f}%", f"{Fore.MAGENTA}{bybit_lead_percentage:.2f}%", arbitrage_opportunity if "Bybit" in arbitrage_opportunity else "", f"{Fore.YELLOW}{bybit_twap:.2f}" if bybit_twap else "N/A", f"{Fore.RED}Yes" if bybit_twap_detected else "No", f"{Fore.YELLOW}{bybit_twap_direction}" if bybit_twap_direction else "N/A", f"{Fore.YELLOW}{bybit_twap_order_size:.2f}" if bybit_twap_order_size else "N/A"],
                ["Coinbase", f"{Fore.GREEN}{coinbase_price}", f"{Fore.CYAN}{difference_percentage_bybit_coinbase:.2f}% / {difference_percentage_binance_coinbase:.2f}%", f"{Fore.MAGENTA}{coinbase_lead_percentage:.2f}%", arbitrage_opportunity if "Coinbase" in arbitrage_opportunity else "", f"{Fore.YELLOW}{coinbase_twap:.2f}" if coinbase_twap else "N/A", f"{Fore.RED}Yes" if coinbase_twap_detected else "No", f"{Fore.YELLOW}{coinbase_twap_direction}" if coinbase_twap_direction else "N/A", f"{Fore.YELLOW}{coinbase_twap_order_size:.2f}" if coinbase_twap_order_size else "N/A"]
            ]

            print(f"\n{Fore.YELLOW}Arbitrage Finder and TWAP Detection by Tyler Simpson\n")
            print(tabulate(table, headers=headers, tablefmt="grid"))
            print(f"{Fore.BLUE}Currently targeted token: {symbol}\n")
        else:
            print(f"{Fore.RED}Could not retrieve prices for all exchanges. Skipping calculation.")

        time.sleep(0.2)  # Sleep for 0.2 seconds to print approximately 5 times a second

if __name__ == "__main__":
    main()
