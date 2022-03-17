import re
from typing import List
from binance.client import Client
from cachetools import cached, TTLCache


class BinanceClient:
    def __init__(self, api_key, secret_key):
        self.client = Client(api_key, secret_key)

    def get_symbols_by_client_order_id(self, order_id_regex: str) -> List:
        return {
            ord["symbol"]
            for ord in self.client.get_open_orders()
            if re.match(order_id_regex, ord["clientOrderId"])
        }

    def get_all_orders_by_symbol(self, symbol):
        return self.client.get_all_orders(symbol=symbol)

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_symbol_step_size(self, symbol):
        return self.client.get_symbol_info(symbol=symbol)["filters"][2]["stepSize"]

    def get_base_asset_from_symbol(self, symbol):
        print(f"Attempting to fetch {symbol} base asset from cache")
        return self.__get_symbol_info(symbol)["baseAsset"]

    def get_quote_asset_from_symbol(self, symbol):
        print(f"Attempting to fetch {symbol} quote asset from cache")
        return self.__get_symbol_info(symbol)["quoteAsset"]

    def get_quote_precision(self, symbol):
        print("before get sym info")
        res = self.__get_symbol_info(symbol)["quotePrecision"]
        print(f"res: {res}")
        return res

    @cached(cache=TTLCache(maxsize=100, ttl=7 * 24 * 60 * 60))
    def __get_symbol_info(self, symbol):
        print(f"No cache entry for {symbol}. Fetching from Binance")
        return self.client.get_symbol_info(symbol)

    def get_savings_info_by_asset(self, asset):
        return self.client.get_lending_position(asset=asset)[0]

    def get_asset_balance(self, asset) -> float:
        return float(self.client.get_asset_balance(asset=asset)["free"])
