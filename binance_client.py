import re
from typing import List
from binance.client import Client
from cachetools import cached, TTLCache


class BinanceClient:
    def __init__(self, api_key, secret_key):
        self.client = Client(api_key, secret_key)

    # ---------------------------------------------------------------------------- #
    #                            Exchange Info Endpoints                           #
    # ---------------------------------------------------------------------------- #

    def get_base_asset_from_symbol(self, symbol):
        print(f"Attempting to fetch {symbol} base asset from cache")
        return self.__get_symbol_info(symbol)["baseAsset"]

    def get_quote_asset_from_symbol(self, symbol):
        print(f"Attempting to fetch {symbol} quote asset from cache")
        return self.__get_symbol_info(symbol)["quoteAsset"]

    def get_quote_precision(self, symbol):
        return self.__get_symbol_info(symbol)["quotePrecision"]

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_symbol_step_size(self, symbol):
        """Don't fetch from cached symbol info as step size is something that changes occasionally"""
        return self.client.get_symbol_info(symbol=symbol)["filters"][2]["stepSize"]

    @cached(cache=TTLCache(maxsize=100, ttl=7 * 24 * 60 * 60))
    def __get_symbol_info(self, symbol):
        print(f"No cache entry for {symbol}. Fetching from Binance")
        return self.client.get_symbol_info(symbol)

    # ---------------------------------------------------------------------------- #
    #                                Order Endpoints                               #
    # ---------------------------------------------------------------------------- #

    def get_symbols_by_client_order_id(self, order_id_regex: str) -> List:
        return {
            ord["symbol"] for ord in self.client.get_open_orders() if re.match(order_id_regex, ord["clientOrderId"])
        }

    def get_all_orders_by_symbol(self, symbol):
        return self.client.get_all_orders(symbol=symbol)

    # ---------------------------------------------------------------------------- #
    #                               Account Endpoints                              #
    # ---------------------------------------------------------------------------- #

    def get_available_asset_balance(self, asset) -> float:
        return float(self.__get_asset_balance(asset)["free"])

    def get_total_asset_balance(self, asset) -> float:
        asset_balance = self.__get_asset_balance(asset)
        return float(asset_balance["free"]) + float(asset_balance["locked"])

    def __get_asset_balance(self, asset):
        return self.client.get_asset_balance(asset=asset)

    # ---------------------------------------------------------------------------- #
    #                          Flexible Savings Endpoints                          #
    # ---------------------------------------------------------------------------- #

    # ------------------------ Savings position endpoints ------------------------ #

    def get_available_savings_by_asset(self, asset) -> float:
        return float(self.__get_savings_position_by_asset(asset)["freeAmount"])

    def get_accruing_interest_savings_by_asset(self, asset) -> float:
        free_amt = float(self.__get_savings_position_by_asset(asset)["freeAmount"])
        today_amt = float(self.__get_savings_position_by_asset(asset)["todayPurchasedAmount"])
        return max(free_amt - today_amt, 0)

    def __get_savings_position_by_asset(self, asset):
        return self.client.get_lending_position(asset=asset)[0]

    # ------------------------- Savings product endpoints ------------------------ #

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_product_id(self, asset) -> bool:
        return self.__get_savings_product_by_asset(asset)["productId"]

    def can_purchase_savings_asset(self, asset) -> bool:
        savings_product = self.__get_savings_product_by_asset(asset)
        return bool(savings_product["canPurchase"]) and bool(savings_product["status"] == "PURCHASING")

    def can_redeem_savings_asset(self, asset) -> bool:
        savings_product = self.__get_savings_product_by_asset(asset)
        return bool(savings_product["canRedeem"]) and bool(savings_product["status"] == "PURCHASING")

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_savings_min_purchase_amount_by_asset(self, asset) -> float:
        return float(self.__get_savings_product_by_asset(asset)["minPurchaseAmount"])

    @cached(cache=TTLCache(maxsize=100, ttl=5))
    def __get_savings_product_by_asset(self, asset):
        return [x for x in self.client.get_lending_product_list() if x["asset"] == asset][0]

    # ----------------------- Savings rebalancing endpoints ---------------------- #

    def subscribe_to_savings(self, asset, quantity):
        product_id = self.get_product_id(asset)
        return self.client.purchase_lending_product(productId=product_id, amount=quantity)

    def redeem_from_savings(self, asset, quantity):
        product_id = self.get_product_id(asset)
        return self.client.redeem_lending_product(productId=product_id, amount=quantity, type="FAST")
