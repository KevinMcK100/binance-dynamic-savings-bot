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
        # Only proceed if client order ID matches format for DCA bot
        if re.match(self.order_id_regex, order_event["order_id"]):
            if self.__is_new_or_filled(order_event):
                if self.__is_buy_order(order_event):
                    self.__log_order_event("3Commas BUY order received:\n\n", order_event)
                    self.__handle_new_safety_order(order_event)
                else:
                    self.__log_order_event("3Commas SELL order received:\n\n", order_event)
            else:
                self.__log_order_event("Order status must be NEW or FILLED:\n\n", order_event, send_telegram=False)
        else:
            self.__log_order_event("Non-3Commas order received:\n\n", order_event, send_telegram=False)

    def __is_new_or_filled(self, order):
        return order["status"] == "NEW" or order["status"] == "FILLED"

    def __is_buy_order(self, order):
        return order["side"] == "BUY"

    def __handle_new_safety_order(self, order_event):
        symbol = order_event["symbol"]
        self.savings_evaluation.reevaluate_symbol(symbol)

    def __log_order_event(self, prepend, order_event, send_telegram=True):
        symbol = order_event["symbol"]
        side = order_event["side"]
        qty = order_event["quantity"]
        price = order_event["price"]
        status = order_event["status"]
        client_order_id = order_event["order_id"]

        log = f"{prepend}\tSymbol: {symbol} \n\tSide: {side} \n\tQuantity: {qty} \n\tPrice: {price} \n\tStatus: {status}\n\tOrder ID: {client_order_id}"
        print(log)
        msg = f"{prepend}Symbol: {symbol} \nSide: {side} \nQuantity: {qty} \nPrice: {price} \nStatus: {status}\nOrder ID: {client_order_id}"
        if send_telegram:
            self.telegram_notifier.enqueue_message(msg)
