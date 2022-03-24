import logging, threading
from asset_precision_calculator import AssetPrecisionCalculator
from assets_dataframe import AssetsDataframe
from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier
from typing import Any, Dict, List


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
        assets_dataframe: AssetsDataframe,
        asset_precision_calculator: AssetPrecisionCalculator,
        dry_run: bool = False,
    ):
        self.order_id_regex = order_id_regex
        self.binance_client = binance_client
        self.telegram_notifier = telegram_notifier
        self.dca_volume_scale = dca_volume_scale
        self.assets_dataframe = assets_dataframe
        self.asset_precision_calculator = asset_precision_calculator
        self.dry_run = dry_run
        self.rebalance_failures = set()
        self.rebalance_mutex = threading.Semaphore(1)

    def reevaluate_symbol(self, symbol):
        try:
            self.rebalance_mutex.acquire()
            self.__reevaluate_symbol(symbol)
        except Exception as ex:
            msg = f"Unexpected error occurred while rebalancing for {symbol}. Will not retry. See logs for more details. Exception: {ex}"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            logging.exception(ex)
        finally:
            self.rebalance_mutex.release()

    def rebalance_all_symbols(self):
        try:
            self.rebalance_mutex.acquire()
            self.__rebalance_quote_assets()
        except Exception as ex:
            msg = f"Unexpected error occurred while rebalancing all assets. Will not retry. See logs for more details. Exception: {ex}"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            logging.exception(ex)
        finally:
            self.rebalance_mutex.release()

    # ---------------------------------------------------------------------------- #
    #                     Reevaluate savings for single symbol                     #
    # ---------------------------------------------------------------------------- #

    def __reevaluate_symbol(self, symbol):
        self.telegram_notifier.enqueue_message(f"Reevaluating spot balance for {symbol}")
        current_deal_orders = self.__get_current_deal_orders_by_symbol(symbol)
        if self.__is_safety_order_open(current_deal_orders):
            next_so = self.__calculate_next_order_value(symbol, current_deal_orders)
            quote_asset = self.binance_client.get_quote_asset_from_symbol(symbol)
            self.assets_dataframe.upsert(symbol, next_so, quote_asset)
            if self.__is_rebalance_required(quote_asset):
                self.__rebalance_quote_assets(quote_asset=quote_asset)
            else:
                quote_asset = self.binance_client.get_quote_asset_from_symbol(symbol)
                self.__send_savings_summary_msg(quote_asset, is_rebalanced=False)
        else:
            msg = f"Safety order not yet open for {symbol}"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)

    def __is_safety_order_open(self, current_deal_orders):
        """
        Ensures we have at least one Base Order (FILLED) and one open Safety Order (NEW)
        """
        statuses = set([ord["status"] for ord in current_deal_orders])
        return "FILLED" in statuses and "NEW" in statuses

    def __is_rebalance_required(self, quote_asset):
        orders_sum = self.assets_dataframe.sum_next_orders(quote_asset)
        orders_max = self.assets_dataframe.max_next_orders(quote_asset)
        min_balance_required = max(orders_sum * 0.5, orders_max)
        current_spot_balance = self.binance_client.get_available_asset_balance(quote_asset)
        return current_spot_balance < min_balance_required

    # ---------------------------------------------------------------------------- #
    #                 Rebalance savings for one or all quote assets                #
    # ---------------------------------------------------------------------------- #

    def __rebalance_quote_assets(self, quote_asset=None):
        active_symbols = self.binance_client.get_symbols_by_client_order_id(self.order_id_regex)
        quote_assets = self.__get_quote_assets(active_symbols) if quote_asset is None else set(quote_asset)
        self.telegram_notifier.enqueue_message("Reevaluating quote assets: {0}".format(", ".join(quote_assets)))
        for quote_asset in quote_assets:
            self.assets_dataframe.drop_by_quote_asset(quote_asset)
            quote_symbols = self.__filter_symbols_by_quote_asset(active_symbols, quote_asset)
            quote_precision = int(self.binance_client.get_quote_precision(quote_symbols[0]))
            for quote_symbol in quote_symbols:
                deal_orders = self.__get_current_deal_orders_by_symbol(quote_symbol)
                next_so = self.__calculate_next_order_value(quote_symbol, deal_orders)
                self.assets_dataframe.upsert(quote_symbol, next_so, quote_asset)
            current_quote_balance = self.binance_client.get_available_asset_balance(quote_asset)
            required_quote_balance = self.assets_dataframe.sum_next_orders(quote_asset)
            self.rebalance_savings(quote_asset, quote_precision, current_quote_balance, required_quote_balance)

    def __get_quote_assets(self, active_symbols):
        return {self.binance_client.get_quote_asset_from_symbol(sym) for sym in active_symbols}

    def __filter_symbols_by_quote_asset(self, symbols, quote_asset):
        return [sym for sym in symbols if str(sym).endswith(quote_asset)]

    def __get_current_deal_orders_by_symbol(self, symbol) -> List[Dict[str, Any]]:
        orders = self.binance_client.get_all_orders_by_symbol(symbol)
        filtered_orders = self.__filter_orders(orders, ["FILLED", "NEW"], ["BUY"])
        filtered_orders.sort(key=lambda x: x.get("timestamp"), reverse=True)
        # Extract the 3Commas deal ID from the client order ID
        deal_id = str(filtered_orders[0]["order_id"]).split("_")[-2]
        # Get all orders associated with the most recent deal
        return [ord for ord in filtered_orders if deal_id in ord["order_id"]]

    def __calculate_next_order_value(self, symbol, current_deal_orders) -> float:
        step_size = self.binance_client.get_symbol_step_size(symbol)
        open_so = [ord for ord in current_deal_orders if ord["status"] == "NEW"][0]
        next_so_cost = self.__calculate_next_so_cost(open_so, step_size)
        print(f"Next safety order cost: {next_so_cost}")
        return next_so_cost

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

    def __calculate_next_so_cost(self, open_so, step_size):
        step_size_buffer = float(open_so["price"]) * float(step_size)
        return float(open_so["quote_qty"]) * self.dca_volume_scale + step_size_buffer

    # ---------------------------------------------------------------------------- #
    #                           Preform rebalance savings                          #
    # ---------------------------------------------------------------------------- #

    def rebalance_savings(self, quote_asset, quote_precision, current_quote_balance, required_quote_balance):
        rebalance_amount = round(current_quote_balance - required_quote_balance, quote_precision)
        if rebalance_amount < 0:
            rebalance_amount = abs(rebalance_amount)
            self.__redeem_asset_from_savings(quote_asset, rebalance_amount)
        elif rebalance_amount > 0:
            self.__subscribe_asset_to_savings(quote_asset, rebalance_amount)
        else:
            print("No rebalancing required")
            self.telegram_notifier.enqueue_message(f"No rebalancing required")

    def __redeem_asset_from_savings(self, asset, quantity):
        """
        Move an amount of the asset from Flexible Savings to Spot Wallet
        """
        print(f"Redeeming {quantity} {asset} to Spot Wallet")
        precision = self.asset_precision_calculator.get_asset_precision(asset)
        rounded_qty = f"%.{precision}f" % quantity

        # Notify user if we do not have enough in Flexible Savings to fund Spot Wallet requirements. In this case we will proceed to redeem all funds remaining
        savings_amount = self.binance_client.get_available_savings_by_asset(asset)
        if savings_amount < quantity:
            rounded_savings = f"%.{precision}f" % savings_amount
            msg = f"Not enough enough {asset} funds to cover upcoming Safety Orders. Moving all Flexible Savings to Spot Wallet. Required amount: {rounded_qty} {asset} Flexible Savings: {rounded_savings} {asset}"
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
            if self.dry_run == False:
                self.binance_client.redeem_from_savings(asset, quantity)
            else:
                msg = f"Running in dry-run mode. Will not move any funds"
                print(msg)
                self.telegram_notifier.enqueue_message(msg)

            msg = f"Moved {rounded_qty} {asset} to Spot Wallet from Flexible Savings"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.__send_savings_summary_msg(asset)
        except Exception as err:
            logging.exception(f"Exception occurred when attempting to rebalance savings for {asset}: {err}")
            print(f"Adding failed asset {asset} to failure set for retrying...")
            self.telegram_notifier.enqueue_message(
                f"Error occurred when rebalancing asset {asset}. Will retry. See logs for details"
            )
            self.rebalance_failures.add(asset)

    def __subscribe_asset_to_savings(self, asset, quantity):
        """
        Move an amount of the asset from Spot Wallet to Flexible Savings
        """
        print(f"Subscribing {quantity} {asset} to Flexible Savings")
        precision = self.asset_precision_calculator.get_asset_precision(asset)
        rounded_qty = f"%.{precision}f" % quantity

        # Ensure we are not attempting to subscribe less than the minimum allowed amount
        min_purchase_amount = self.binance_client.get_savings_min_purchase_amount_by_asset(asset)
        if quantity < min_purchase_amount:
            msg = f"{rounded_qty} {asset} is less than the minimum Flexible Savings purchase amount. Will not rebalance {asset} asset."
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
            if self.dry_run == False:
                self.binance_client.subscribe_to_savings(asset, quantity)
            else:
                msg = f"Running in dry-run mode. Will not move any funds"
                print(msg)
                self.telegram_notifier.enqueue_message(msg)
            msg = f"Moved {rounded_qty} {asset} from Spot Wallet to Flexible Savings"
            print(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.__send_savings_summary_msg(asset)
        except Exception as err:
            logging.exception(f"Exception occurred when attempting to rebalance savings for {asset}: {err}")
            print(f"Adding failed asset {asset} to failure set for retrying...")
            self.telegram_notifier.enqueue_message(
                f"Error occurred when rebalancing asset {asset}. Will attempt to retry. See logs for details"
            )
            self.rebalance_failures.add(asset)

    def __send_savings_summary_msg(self, asset, is_rebalanced=True):
        precision = self.asset_precision_calculator.get_asset_precision(asset)
        available_spot = f"%.{precision}f" % self.binance_client.get_available_asset_balance(asset)
        total_spot = f"%.{precision}f" % self.binance_client.get_total_asset_balance(asset)
        available_savings = f"%.{precision}f" % self.binance_client.get_available_savings_by_asset(asset)
        accruing_interest = f"%.{precision}f" % self.binance_client.get_accruing_interest_savings_by_asset(asset)
        prepend_msg = (
            f"{asset} savings rebalanced." if is_rebalanced == True else f"{asset} savings did not need rebalanced."
        )
        msg = f"{prepend_msg}\n\nSpot Available: {available_spot} {asset}\nSpot Total: {total_spot} {asset}\n\nSavings Available: {available_savings} {asset}\nAccruing Interest: {accruing_interest} {asset}"
        print(msg)
        self.telegram_notifier.enqueue_message(msg)
