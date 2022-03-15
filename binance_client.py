import re
from typing import List
from binance.client import Client


class BinanceClient:
    def __init__(self, api_key, secret_key):
        self.client = Client(api_key, secret_key)

    def get_symbols_by_client_order_id(self, order_id_regex: str) -> List:
        return {
            ord["symbol"]
            for ord in self.client.get_open_orders()
            if re.match(order_id_regex, ord["clientOrderId"])
        }

    def get_symbol_step_size(self, symbol):
        return self.client.get_symbol_info(symbol=symbol)["filters"][2]["stepSize"]

    def get_all_orders_by_symbol(self, symbol):
        return self.client.get_all_orders(symbol=symbol)
