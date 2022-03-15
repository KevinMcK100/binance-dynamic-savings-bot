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
            # Temporarily process non-3Commas orders for ease of testing
            if "deal" in order_event["client_order_id"]:
                print(order_event)
                self.telegram_notifier.send_message(order_event)

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
        step_size = self.binance_client.get_symbol_step_size(symbol)
        orders = self.binance_client.get_all_orders_by_symbol(symbol)

        filtered_orders = self.filter_orders(orders, ["FILLED", "NEW"], ["BUY"])
        filtered_orders.sort(key=lambda x: x.get("timestamp"), reverse=True)
        # filtered_orders.index()

        # Extract the 3Commas deal ID from the client order ID
        deal_id = str(filtered_orders[0]["order_id"]).split("_")[-2]
        print(deal_id)
        # Get all orders associated with the most recent deal
        current_deal_orders = [
            ord for ord in filtered_orders if deal_id in ord["order_id"]
        ]
        print()
        for order in current_deal_orders:
            print(order)
        print()
        # Delete the Base Order to leave just the Safety Orders
        # del current_deal_orders[-1]

        for order in current_deal_orders:
            print(order)

        if self.is_safety_order_open(current_deal_orders):
            open_so = [ord for ord in current_deal_orders if ord["status"] == "NEW"][0]
            print()
            next_so_cost = self.calculate_next_so_cost(open_so, step_size)
            print(next_so_cost)
            self.telegram_notifier.send_message(
                f"Next Safety Order cost: {next_so_cost} USDT"
            )
        else:
            print("Must have FILLED and NEW orders in order list")

    def filter_orders(self, orders, statuses, sides):
        return [
            {
                "price": ord["price"],
                "quote_qty": round(float(ord["origQty"]) * float(ord["price"]), 2),
                "qty": ord["origQty"],
                "order_id": ord["clientOrderId"],
                "timestamp": ord["time"],
                "status": ord["status"],
                "side": ord["side"],
            }
            for ord in orders
            if (ord["status"] in statuses and ord["side"] in sides)
        ]

    def is_safety_order_open(self, current_deal_orders):
        # Ensures we have at least one Base Order (FILLED) and one open Safety Order (NEW)
        return len(set([ord["status"] for ord in current_deal_orders])) == 2

    def calculate_next_so_cost(self, open_so, step_size):
        step_size_buffer = float(open_so["price"]) * float(step_size)
        return float(open_so["quote_qty"]) * 1.05 + step_size_buffer
