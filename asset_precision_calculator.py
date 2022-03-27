from cachetools import cached
import numpy as np
from binance_client import BinanceClient
import logging
from functools import lru_cache


class AssetPrecisionCalculator:
    def __init__(self, binance_client: BinanceClient):
        self.binance_client = binance_client

    @lru_cache(maxsize=None)
    def get_asset_precision(self, asset: str):
        logging.info(f"Getting presicion for asset: {asset}")
        precision = 2
        try:
            # Get price of asset in dollars
            price = 1 if asset == "USDT" else self.binance_client.get_cached_symbol_price(asset + "USDT")
            # Default precision against USDT is 2 DP. Add number of exponents to get realistic rounding precision (lowest precision of 0)
            precision = max(2 + self.__get_exponents(price), 0)
        except Exception:
            logging.exception(f"Error getting precision for asset {asset}. Defaulting to 2 DP.")
        logging.info(f"Calculated precision at {precision} DP for asset {asset}")
        return precision

    def __get_exponents(self, price: float):
        return int(np.floor(np.log10(np.abs(price))))
