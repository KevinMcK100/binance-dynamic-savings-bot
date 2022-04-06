import logging
from asset_precision_calculator import AssetPrecisionCalculator
from balance_update import BalanceUpdate
from binance_client import BinanceClient
from savings_evaluation import SavingsEvaluation
from telegram_notifier import TelegramNotifier


class BalanceUpdateProcessor:
    def __init__(
        self,
        order_id_regex: str,
        binance_client: BinanceClient,
        savings_evaluation: SavingsEvaluation,
    ):
        self.order_id_regex = order_id_regex
        self.binance_client = binance_client
        self.savings_evaluation = savings_evaluation

    def process_balance_update(self, balance_update: BalanceUpdate):
        active_symbols = self.binance_client.get_symbols_by_client_order_id(self.order_id_regex)
        quote_assets = {self.binance_client.get_quote_asset_from_symbol(sym) for sym in active_symbols}
        if balance_update.asset in quote_assets:
            self.savings_evaluation.send_savings_summary_msg(balance_update.asset)
        else:
            logging.info(f"Dropping Balance Update Event {balance_update}. Asset not active in DCA bot")
