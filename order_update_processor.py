import logging
import re

from binance_client import BinanceClient
from order import Order
from savings_evaluation import SavingsEvaluation
from telegram_notifier import TelegramNotifier


class OrderUpdateProcessor:
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

    def process_order(self, order: Order):
        # Only proceed if client order ID matches format for DCA bot
        if re.match(self.order_id_regex, order.order_id):
            self.__handle_buy_order(order) if order.is_buy_order() else self.__handle_sell_order(order)
        else:
            self.__log_order_event("Non-3Commas order received:\n\n", order, verbose=True)

    # ---------------------------------------------------------------------------- #
    #                               Handle BUY orders                              #
    # ---------------------------------------------------------------------------- #
    def __handle_buy_order(self, order: Order):
        if order.is_new_order():
            self.__log_order_event("New BUY order received:\n\n", order)
            self.savings_evaluation.reevaluate_symbol(order.symbol, order)
        else:
            self.__log_order_event("Order status must be NEW to trigger reevaluation:\n\n", order, verbose=True)

    # ---------------------------------------------------------------------------- #
    #                              Handle SELL orders                              #
    # ---------------------------------------------------------------------------- #
    def __handle_sell_order(self, order: Order):
        if order.is_filled_order():
            self.__log_order_event("Take Profit Hit 💰\n\n", order)
        else:
            self.__log_order_event("3Commas SELL order received:\n\n", order, verbose=True)

    # ---------------------------------------------------------------------------- #
    #                             Messaging and logging                            #
    # ---------------------------------------------------------------------------- #
    def __log_order_event(self, prepend, ord: Order, verbose: bool = False):
        price = str(ord.price) + " " + ord.quote_asset
        total = str(ord.quote_qty) + " " + ord.quote_asset
        log = f"{prepend}\tSymbol: {ord.symbol} \n\tSide: {ord.side} \n\tQuantity: {ord.quantity} \n\tPrice: {price} \n\tTotal: {total} \n\tStatus: {ord.status}\n\tOrder ID: {ord.order_id}"
        logging.info(log)
        msg = f"{prepend}Symbol: {ord.symbol} \nSide: {ord.side} \nQuantity: {ord.quantity} \nPrice: {price} \nTotal: {total} \nStatus: {ord.status}\nOrder ID: {ord.order_id}"
        self.telegram_notifier.enqueue_message(msg, verbose)
