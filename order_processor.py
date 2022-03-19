import re
from binance_client import BinanceClient
from savings_evaluation import SavingsEvaluation
from telegram_notifier import TelegramNotifier


class OrderProcessor:
    def __init__(
        self,
        order_id_regex: str,
        binance_client: BinanceClient,
        savings_evaluation: SavingsEvaluation,
        telegram_notifier: TelegramNotifier,
    ):
        self.order_id_regex = order_id_regex
        self.binance_client = binance_client
        self.savings_evaluation = savings_evaluation
        self.telegram_notifier = telegram_notifier

    def process_order(self, order_event: dict):
        if order_event["event_type"] == "executionReport":
            # Only proceed if client order ID matches format for DCA bot
            if re.match(self.order_id_regex, order_event["client_order_id"]):

                self.__log_order_event("3Commas order received:\n\n", order_event)
                self.__handle_new_safety_order(order_event)
                # logging.info(order_event)
            else:
                self.__log_order_event("Non-3Commas order received:\n\n", order_event)

    def __handle_new_safety_order(self, order_event):
        side = order_event["side"]
        symbol = order_event["symbol"]
        self.telegram_notifier.send_message(f"{side} order event received on {symbol}")
        self.savings_evaluation.reevaluate_symbol(symbol)

    def __log_order_event(self, prepend, order_event):
        symbol = order_event["symbol"]
        side = order_event["side"]
        qty = order_event["order_quantity"]
        price = order_event["order_price"]
        status = order_event["current_order_status"]
        client_order_id = order_event["client_order_id"]

        log = f"{prepend}\tSymbol: {symbol} \n\tSide: {side} \n\tQuantity: {qty} \n\tPrice: {price} \n\tStatus: {status}\n\tOrder ID: {client_order_id}"
        print(log)
        msg = f"{prepend}Symbol: {symbol} \nSide: {side} \nQuantity: {qty} \nPrice: {price} \nStatus: {status}\nOrder ID: {client_order_id}"
        self.telegram_notifier.send_message(msg)
