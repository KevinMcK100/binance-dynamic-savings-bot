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
        active_symbols = self.binance_client.get_symbols_by_client_order_id(
            self.order_id_regex
        )
        self.telegram_notifier.send_message(
            "Active currency pairs: \n\n{0}".format("\n".join(active_symbols))
        )
        balance_required = 0
        quote_assets = self.get_quote_assets(active_symbols)
        self.telegram_notifier.send_message(
            "Quote assets to rebalance: {0}".format(", ".join(quote_assets))
        )
        for quote_asset in quote_assets:
            print(f"Rebalancing all assets paired with {quote_asset} quote asset")
            # Get all symbols which match the quote asset. Eg, all symbols ending with USDT or USDC or BTC
            quote_symbols = [
                sym for sym in active_symbols if str(sym).endswith(quote_asset)
            ]
            print(f"All assets to rebalance: {quote_symbols}")
            savings_info = self.binance_client.get_savings_info_by_asset(quote_asset)
            quote_precision = int(
                self.binance_client.get_quote_precision(quote_symbols[0])
            )
            print(savings_info)
            current_quote_savings = round(
                float(savings_info["freeAmount"]), quote_precision
            )
            self.telegram_notifier.send_message(
                f"Amount redeemable: {current_quote_savings} {quote_asset} "
            )

            total_quote_required = sum(
                [self.calculate_next_order_value(sym) for sym in quote_symbols]
            )
            print(f"Total quote required: {total_quote_required}")
            quote_balance = self.binance_client.get_asset_balance(quote_asset)
            self.rebalance_savings(
                quote_asset,
                quote_precision,
                quote_balance,
                total_quote_required,
                current_quote_savings,
            )
        print(f"Active quote assets: {quote_assets}")
        # for symbol in active_symbols:
        #     base_asset = self.binance_client.get_base_asset_from_symbol(symbol)
        #     print(f"Base asset: {base_asset}")
        #     quote_asset = self.binance_client.get_quote_asset_from_symbol(symbol)
        #     print(f"Quote asset: {quote_asset}")
        #     balance_required += self.calculate_next_order_value(symbol)
        # self.telegram_notifier.send_message(
        #     f"Total USDT required for all assets: {quote_assets}"
        # )

    def get_quote_assets(self, active_symbols):
        return {
            self.binance_client.get_quote_asset_from_symbol(sym)
            for sym in active_symbols
        }

    def calculate_next_order_value(self, symbol) -> float:
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
            print(f"Next safety order cost: {next_so_cost}")
            return next_so_cost
        else:
            print("Must have FILLED and NEW orders in order list")

        return None

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

    def rebalance_savings(
        self, asset, asset_precision, spot_balance, spot_required, savings_balance
    ):
        rebalance_amount = round(abs(spot_balance - spot_required), asset_precision)
        if spot_balance < spot_required:
            print(f"Attempting to move {rebalance_amount} {asset} from savings to spot")
            self.telegram_notifier.send_message(
                f"Attempting to move {rebalance_amount} {asset} from savings to spot"
            )
        elif spot_balance > spot_required:
            print(f"Attempting to move {rebalance_amount} {asset} from spot to savings")
            self.telegram_notifier.send_message(
                f"Attempting to move {rebalance_amount} {asset} from spot to savings"
            )
        else:
            print("No rebalancing required")
            self.telegram_notifier.send_message(f"No rebalancing required")
