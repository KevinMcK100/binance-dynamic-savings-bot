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
        self.telegram_notifier.send_message(f"Received order event: {order_event}")
        if order_event["event_type"] == "executionReport":
            # Temporarily process non-3Commas orders for ease of testing
            if "deal" in order_event["client_order_id"]:
                print(order_event)
                self.telegram_notifier.send_message(f"3Commas order: {order_event}")

                # logging.info(order_event)
            else:
                print("Non-3Commas order received")
                print(order_event)

                symbol = order_event["symbol"]
                side = order_event["side"]
                qty = order_event["order_quantity"]
                price = order_event["order_price"]
                status = order_event["current_order_status"]
                self.telegram_notifier.send_message(
                    f"Non-3Commas order received. \n\nSymbol: {symbol} \nSide: {side} \nQuantity: {qty} \nPrice: {price} \nStatus: {status}"
                )
            self.handle_new_safety_order(order_event)

    def handle_new_safety_order(self, order_event):
        side = order_event["side"]
        symbol = order_event["symbol"]
        self.telegram_notifier.send_message(f"{side} order event received on {symbol}")
        next_so_price = self.savings_evaluation.calculate_next_order_value(symbol)
        quote_asset = self.binance_client.get_base_asset_from_symbol(symbol)
        self.telegram_notifier.send_message(
            f"Next Safety Order cost: {next_so_price} {quote_asset}"
        )
        print(next_so_price)
