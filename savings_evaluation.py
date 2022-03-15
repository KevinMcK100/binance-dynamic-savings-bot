from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier


class SavingsEvaluation:
    def __init__(
        self,
        order_id_regex: str,
        binance_client: BinanceClient,
        telegram_notifier: TelegramNotifier,
    ):
        self.order_id_regex = order_id_regex
        self.binance_client = binance_client
        self.telegram_notifier = telegram_notifier

    def reevaluate_all_symbols(self):
        self.telegram_notifier.send_message("Reevaluating all Symbols...")
        list = ", ".join(
            self.binance_client.get_symbols_by_client_order_id(self.order_id_regex)
        )
        self.telegram_notifier.send_message(list)
