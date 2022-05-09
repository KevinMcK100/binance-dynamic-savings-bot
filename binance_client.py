import logging
import re
from typing import List

from binance.client import Client
from cachetools import TTLCache, cached

from order import Order


class BinanceClient:
    def __init__(self, api_key, secret_key):
        self.client = Client(api_key, secret_key)

    # ---------------------------------------------------------------------------- #
    #                            Exchange Info Endpoints                           #
    # ---------------------------------------------------------------------------- #

    def get_base_asset_from_symbol(self, symbol) -> str:
        logging.debug(f"Attempting to fetch {symbol} base asset from cache")
        return str(self.__get_symbol_info(symbol)["baseAsset"])

    def get_quote_asset_from_symbol(self, symbol) -> str:
        logging.debug(f"Attempting to fetch {symbol} quote asset from cache")
        return str(self.__get_symbol_info(symbol)["quoteAsset"])

    def get_quote_precision(self, symbol) -> int:
        return int(self.__get_symbol_info(symbol)["quotePrecision"])

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_cached_symbol_price(self, symbol) -> float:
        return float(self.client.get_avg_price(symbol=symbol)["price"])

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_symbol_step_size(self, symbol):
        """Don't fetch from cached symbol info as step size is something that changes occasionally"""
        return self.client.get_symbol_info(symbol=symbol)["filters"][2]["stepSize"]

    @cached(cache=TTLCache(maxsize=100, ttl=7 * 24 * 60 * 60))
    def __get_symbol_info(self, symbol):
        logging.debug(f"No cache entry for {symbol}. Fetching from Binance")
        return self.client.get_symbol_info(symbol)

    # ---------------------------------------------------------------------------- #
    #                                Order Endpoints                               #
    # ---------------------------------------------------------------------------- #

    def get_symbols_by_client_order_id(self, order_id_regex: str) -> List:
        open_orders = [self.__map_order(ord) for ord in self.client.get_open_orders()]
        return [ord.symbol for ord in open_orders if re.match(order_id_regex, ord.order_id)]

    def get_all_orders_by_symbol(self, symbol) -> List[Order]:
        return [self.__map_order(ord) for ord in self.client.get_all_orders(symbol=symbol)]

    def __map_order(self, order) -> Order:
        symbol = order["symbol"]
        base_asset = self.get_base_asset_from_symbol(symbol)
        quote_asset = self.get_quote_asset_from_symbol(symbol)
        return Order(
            symbol,
            base_asset,
            quote_asset,
            float(order["price"]),
            float(order["origQty"]),
            order["clientOrderId"],
            order["status"],
            order["side"],
            order["time"],
        )

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
        asset_savings = self.__get_savings_position_by_asset(asset)
        if asset_savings is not None:
            return float(self.__get_savings_position_by_asset(asset)["freeAmount"])
        return 0

    def get_accruing_interest_savings_by_asset(self, asset) -> float:
        free_amt = self.get_available_savings_by_asset(asset)
        today_amt = self.__get_today_purchased_amount_by_asset(asset)
        return max(free_amt - today_amt, 0)

    def __get_today_purchased_amount_by_asset(self, asset) -> float:
        asset_savings = self.__get_savings_position_by_asset(asset)
        if asset_savings is not None:
            return float(self.__get_savings_position_by_asset(asset)["todayPurchasedAmount"])
        return 0

    def __get_savings_position_by_asset(self, asset):
        lending_position = self.client.get_lending_position(asset=asset)
        if lending_position is not None and len(lending_position) > 0:
            return lending_position[0]
        return None

    # ------------------------- Savings product endpoints ------------------------ #

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_product_id(self, asset) -> str:
        savings_product = self.__get_savings_product_by_asset(asset)
        if savings_product is None:
            raise RuntimeError(f"Could not get product ID for savings product for asset {asset}")
        return savings_product["productId"]

    def can_purchase_savings_asset(self, asset) -> bool:
        savings_product = self.__get_savings_product_by_asset(asset)
        return (
            savings_product is not None
            and bool(savings_product["canPurchase"])
            and savings_product["status"] == "PURCHASING"
        )

    def can_redeem_savings_asset(self, asset) -> bool:
        savings_product = self.__get_savings_product_by_asset(asset)
        return (
            savings_product is not None
            and bool(savings_product["canRedeem"])
            and savings_product["status"] == "PURCHASING"
        )

    @cached(cache=TTLCache(maxsize=100, ttl=24 * 60 * 60))
    def get_savings_min_purchase_amount_by_asset(self, asset) -> float:
        savings_product = self.__get_savings_product_by_asset(asset)
        if savings_product is not None:
            return float(savings_product["minPurchaseAmount"])
        else:
            return 0.0

    @cached(cache=TTLCache(maxsize=100, ttl=5))
    def __get_savings_product_by_asset(self, asset):
        page_size, page_count = 100, 1
        while True:
            product_list = self.client.get_lending_product_list(size=page_size, current=page_count)
            asset_product = [x for x in product_list if x["asset"] == asset]
            if len(asset_product) > 0:
                return asset_product[0]
            elif len(product_list) < page_size:
                logging.warn(f"Couldn't get lending product for asset {asset} from lending product list")
                return None
            page_count = page_count + 1

    # ----------------------- Savings rebalancing endpoints ---------------------- #

    def subscribe_to_savings(self, asset, quantity):
        product_id = self.get_product_id(asset)
        return self.client.purchase_lending_product(productId=product_id, amount=quantity)

    def redeem_from_savings(self, asset, quantity):
        product_id = self.get_product_id(asset)
        return self.client.redeem_lending_product(productId=product_id, amount=quantity, type="FAST")
