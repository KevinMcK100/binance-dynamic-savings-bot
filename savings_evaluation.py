import logging, threading
from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier
from telegram.error import TelegramError


class SavingsEvaluation:
    """
    Class responsible for calculating and rebalancing assets between Spot Wallet and Flexible Savings.

    There are multiple routes into this code from separate threads:
        - Binance websocket order events triggered
        - User executes Telegram command
        - Rebalancing failure handler executing retries

    In order to avoid race conditions during rebalancing calculations, we must treat this code as synchronous.
    We use a Semaphore here to achieve this.
    """

    def __init__(
        self,
        order_id_regex: str,
        binance_client: BinanceClient,
        telegram_notifier: TelegramNotifier,
        dca_volume_scale: float,
    ):
        self.order_id_regex = order_id_regex
        self.binance_client = binance_client
        self.telegram_notifier = telegram_notifier
        self.dca_volume_scale = dca_volume_scale
        self.rebalance_failures = set()
        self.rebalance_mutex = threading.Semaphore(1)

    def reevaluate_symbol(self, symbol):
        try:
            self.rebalance_mutex.acquire()
            self.__reevaluate_symbol(symbol)
        except TelegramError as ex:
            logging.exception(f"Exception occurred sending Telegram notification for {symbol}: {ex}")
            print(f"Exception occurred sending Telegram notification for {symbol}: {ex}")
        except Exception as ex:
            msg = f"Unexpected error occurred while rebalancing for {symbol}. Will not retry. See logs for more details. Exception: {ex}"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            logging.exception(ex)
        finally:
            self.rebalance_mutex.release()

    def reevaluate_all_symbols(self):
        try:
            self.rebalance_mutex.acquire()
            self.__reevaluate_all_symbols()
        except TelegramError as ex:
            logging.exception(f"Exception occurred sending Telegram notification on reevaluate all symbols: {ex}")
            print(f"Exception occurred sending Telegram notification for reevaluate all symbols: {ex}")
        except Exception as ex:
            msg = f"Unexpected error occurred while rebalancing all assets. Will not retry. See logs for more details. Exception: {ex}"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            logging.exception(ex)
        finally:
            self.rebalance_mutex.release()

    def __reevaluate_symbol(self, symbol):
        self.telegram_notifier.enqueue_message(f"Reevaluating savings for {symbol}...")
        quote_asset = list(self.__get_quote_assets([symbol]))[0]
        quote_precision = int(self.binance_client.get_quote_precision(symbol))
        next_order_cost = self.__calculate_next_order_value(symbol)
        # We do not queue for retry here because we expect a subsequent order event to be triggered once Safety Order has been placed by DCA bot
        if next_order_cost is None:
            return
        quote_balance = self.binance_client.get_available_asset_balance(quote_asset)
        self.rebalance_savings(quote_asset, quote_precision, quote_balance, next_order_cost)

    def __reevaluate_all_symbols(self):
        self.telegram_notifier.enqueue_message("Reevaluating all Symbols...")
        active_symbols = self.binance_client.get_symbols_by_client_order_id(self.order_id_regex)
        self.telegram_notifier.enqueue_message("Active currency pairs: \n\n{0}".format("\n".join(active_symbols)))
        quote_assets = self.__get_quote_assets(active_symbols)
        self.telegram_notifier.enqueue_message("Quote assets to rebalance: {0}".format(", ".join(quote_assets)))
        print(f"Active quote assets: {quote_assets}")
        for quote_asset in quote_assets:
            print(f"Rebalancing all assets paired with {quote_asset} quote asset")
            # Get all symbols which match the quote asset. Eg, all symbols ending with USDT or USDC or BTC
            quote_symbols = [sym for sym in active_symbols if str(sym).endswith(quote_asset)]
            print(f"All assets to rebalance: {quote_symbols}")
            quote_precision = int(self.binance_client.get_quote_precision(quote_symbols[0]))
            # If any one calculation returns None (ie. doesn't have Safety Order set) then treat as a failure and queue for retry
            try:
                total_quote_required = sum([self.__calculate_next_order_value(sym) for sym in quote_symbols])
            except TypeError as err:
                err_msg = f"Unable to preform rebalancing calculations for {quote_asset} as some base assets don't have Safety Orders in place yet. Queueing for retry."
                logging.exception(f"{err_msg} Error: {err}")
                self.telegram_notifier.enqueue_message(err_msg)
                self.rebalance_failures.add(quote_asset)
                return

            print(f"Total quote required: {total_quote_required}")
            quote_balance = self.binance_client.get_available_asset_balance(quote_asset)
            self.rebalance_savings(quote_asset, quote_precision, quote_balance, total_quote_required)

    def __calculate_next_order_value(self, symbol) -> float:
        step_size = self.binance_client.get_symbol_step_size(symbol)
        orders = self.binance_client.get_all_orders_by_symbol(symbol)

        filtered_orders = self.__filter_orders(orders, ["FILLED", "NEW"], ["BUY"])
        filtered_orders.sort(key=lambda x: x.get("timestamp"), reverse=True)

        # Extract the 3Commas deal ID from the client order ID
        deal_id = str(filtered_orders[0]["order_id"]).split("_")[-2]
        print(f"3Commas deal ID: {deal_id}")
        # Get all orders associated with the most recent deal
        current_deal_orders = [ord for ord in filtered_orders if deal_id in ord["order_id"]]

        if self.__is_safety_order_open(current_deal_orders):
            open_so = [ord for ord in current_deal_orders if ord["status"] == "NEW"][0]
            next_so_cost = self.__calculate_next_so_cost(open_so, step_size)
            print(f"Next safety order cost: {next_so_cost}")
            return next_so_cost
        else:
            print("Must have FILLED and NEW orders in order list")

        return None

    def __get_quote_assets(self, active_symbols):
        return {self.binance_client.get_quote_asset_from_symbol(sym) for sym in active_symbols}

    def __filter_orders(self, orders, statuses, sides):
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

    def __is_safety_order_open(self, current_deal_orders):
        # Ensures we have at least one Base Order (FILLED) and one open Safety Order (NEW)
        return len(set([ord["status"] for ord in current_deal_orders])) == 2

    def __calculate_next_so_cost(self, open_so, step_size):
        step_size_buffer = float(open_so["price"]) * float(step_size)
        return float(open_so["quote_qty"]) * self.dca_volume_scale + step_size_buffer

    def rebalance_savings(self, asset, asset_precision, spot_balance, spot_required):
        rebalance_amount = round(abs(spot_balance - spot_required), asset_precision)
        if spot_balance < spot_required:
            print(f"Attempting to move {rebalance_amount} {asset} from savings to spot")
            self.telegram_notifier.enqueue_message(
                f"Attempting to move {rebalance_amount} {asset} from savings to spot"
            )
            self.__redeem_asset_from_savings(asset, rebalance_amount)
        elif spot_balance > spot_required:
            print(f"Attempting to move {rebalance_amount} {asset} from spot to savings")
            self.telegram_notifier.enqueue_message(
                f"Attempting to move {rebalance_amount} {asset} from spot to savings"
            )
            self.__subscribe_asset_to_savings(asset, rebalance_amount)
        else:
            print("No rebalancing required")
            self.telegram_notifier.enqueue_message(f"No rebalancing required")

    def __subscribe_asset_to_savings(self, asset, quantity):
        """
        Move an amount of the asset from Spot Wallet to Flexible Savings
        """
        print(f"Subscribing {quantity} {asset} to Flexible Savings")

        # Ensure we are not attempting to subscribe less than the minimum allowed amount
        min_purchase_amount = self.binance_client.get_savings_min_purchase_amount_by_asset(asset)
        if quantity < min_purchase_amount:
            msg = f"{quantity} {asset} is less than the minimum Flexible Savings purchase amount. Will not rebalance {asset} asset."
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            return

        # Check if we can subscribe to the asset, if not, add it as a failure for retrying later
        if not self.binance_client.can_purchase_savings_asset(asset):
            msg = f"{asset} is currently unavailable to purchase in Flexible Savings. Will retry when it becomes available"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.rebalance_failures.add(asset)
            return

        # Execute subscription to Flexible Savings
        try:
            # self.binance_client.subscribe_to_savings(asset, quantity)
            msg = f"Moved {quantity} {asset} from Spot Wallet to Flexible Savings"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.__rebalanced_amounts_notifications(asset)
        except TelegramError as err:
            logging.exception(f"Exception occurred sending Telegram notification for {asset}: {err}")
            print(f"Exception occurred sending Telegram notification for {asset}: {err}")
        except Exception as err:
            logging.exception(f"Exception occurred when attempting to rebalance savings for {asset}: {err}")
            print(f"Adding failed asset {asset} to failure set for retrying...")
            self.telegram_notifier.enqueue_message(
                f"Error occurred when rebalancing asset {asset}. Will attempt to retry. See logs for details"
            )
            self.rebalance_failures.add(asset)

    def __redeem_asset_from_savings(self, asset, quantity):
        """
        Move an amount of the asset from Flexible Savings to Spot Wallet
        """
        print(f"Redeeming {quantity} {asset} to Spot Wallet")

        # Notify user if we do not have enough in Flexible Savings to fund Spot Wallet requirements. In this case we will proceed to redeem all funds remaining
        savings_amount = self.binance_client.get_available_savings_by_asset(asset)
        if savings_amount < quantity:
            msg = f"Not enough enough {asset} funds to cover upcoming Safety Orders. Moving all Flexible Savings to Spot Wallet. Required amount: {quantity} {asset} Flexible Savings: {savings_amount} {asset}"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            quantity = savings_amount

        # Check if we can redeem from the asset, if not, add it as a failure for retrying later
        if not self.binance_client.can_redeem_savings_asset(asset):
            msg = f"{asset} is currently unavailable to redeem from Flexible Savings. Will retry when it becomes available"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.rebalance_failures.add(asset)
            return

        # Execute redemption from Flexible Savings
        try:
            # self.binance_client.redeem_from_savings(asset, quantity)
            msg = f"Moved {quantity} {asset} to Spot Wallet from Flexible Savings"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.__rebalanced_amounts_notifications(asset)
        except TelegramError as err:
            logging.exception(f"Exception occurred sending Telegram notification for {asset}: {err}")
            print(f"Exception occurred sending Telegram notification for {asset}: {err}")
        except Exception as err:
            logging.exception(f"Exception occurred when attempting to rebalance savings for {asset}: {err}")
            print(f"Adding failed asset {asset} to failure set for retrying...")
            self.telegram_notifier.enqueue_message(
                f"Error occurred when rebalancing asset {asset}. Will retry. See logs for details"
            )
            self.rebalance_failures.add(asset)

    def __rebalanced_amounts_notifications(self, asset):
        available_spot = self.binance_client.get_available_asset_balance(asset)
        total_spot = self.binance_client.get_total_asset_balance(asset)
        available_savings = self.binance_client.get_available_savings_by_asset(asset)
        accruing_interest = self.binance_client.get_accruing_interest_savings_by_asset(asset)
        msg = f"{asset} savings rebalanced.\n\nSpot Wallet Available: {available_spot} {asset}\nSpot Wallet Total: {total_spot} {asset}\n\nAvailable Savings: {available_savings} {asset}\nAccruing Interest: {accruing_interest} {asset}"
        print(msg)
        self.telegram_notifier.enqueue_message(msg)
