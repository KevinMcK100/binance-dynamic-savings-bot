import logging
import threading
from typing import List

from asset_precision_calculator import AssetPrecisionCalculator
from assets_dataframe import AssetsDataframe
from binance_client import BinanceClient
from order import Order
from telegram_notifier import TelegramNotifier


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
        quote_coverage: float,
        assets_dataframe: AssetsDataframe,
        asset_precision_calculator: AssetPrecisionCalculator,
        excluded_symbols: List[str],
        dry_run: bool = False,
    ):
        self.order_id_regex = order_id_regex
        self.binance_client = binance_client
        self.telegram_notifier = telegram_notifier
        self.dca_volume_scale = dca_volume_scale
        self.quote_coverage = quote_coverage
        self.assets_dataframe = assets_dataframe
        self.asset_precision_calculator = asset_precision_calculator
        self.excluded_symbols = excluded_symbols
        self.dry_run = dry_run
        self.rebalance_failures = set()
        self.rebalance_mutex = threading.Semaphore(1)

    def reevaluate_symbol(self, symbol: str, order_event: Order = None):
        try:
            self.rebalance_mutex.acquire()
            self.__reevaluate_symbol(symbol, order_event)
        except Exception as ex:
            msg = f"Unexpected error occurred while rebalancing for {symbol}. Will not retry. See logs for more details. Exception: {ex}"
            self.telegram_notifier.enqueue_message(msg)
            logging.exception(msg)
        finally:
            self.rebalance_mutex.release()

    def rebalance_all_symbols(self):
        try:
            self.rebalance_mutex.acquire()
            self.__rebalance_quote_assets()
        except Exception as ex:
            msg = f"Unexpected error occurred while rebalancing all assets. Will not retry. See logs for more details. Exception: {ex}"
            self.telegram_notifier.enqueue_message(msg)
            logging.exception(msg)
        finally:
            self.rebalance_mutex.release()

    def send_savings_summary_msg(self, asset, is_rebalanced=True):
        precision = self.asset_precision_calculator.get_asset_precision(asset)
        available_spot = f"%.{precision}f" % self.binance_client.get_available_asset_balance(asset)
        total_spot = f"%.{precision}f" % self.binance_client.get_total_asset_balance(asset)
        available_savings = f"%.{precision}f" % self.binance_client.get_available_savings_by_asset(asset)
        accruing_interest = f"%.{precision}f" % self.binance_client.get_accruing_interest_savings_by_asset(asset)
        prepend_msg = (
            f"{asset} savings rebalanced." if is_rebalanced == True else f"{asset} savings did not need rebalanced."
        )
        msg = f"{prepend_msg}\n\nSpot Available: {available_spot} {asset}\nSpot Total: {total_spot} {asset}\n\nSavings Available: {available_savings} {asset}\nAccruing Interest: {accruing_interest} {asset}"
        logging.info(msg)
        self.telegram_notifier.enqueue_message(msg)

    # ---------------------------------------------------------------------------- #
    #                     Reevaluate savings for single symbol                     #
    # ---------------------------------------------------------------------------- #

    def __reevaluate_symbol(self, symbol, order_event: Order = None):
        current_deal_orders = self.__get_current_deal_orders_by_symbol(symbol)
        if order_event is not None:
            current_deal_orders = self.__upsert_order_to_orders(order_event, current_deal_orders)
        self.__log_orders(current_deal_orders, "Current Deal Orders")
        if self.__is_safety_order_open(current_deal_orders):
            self.telegram_notifier.enqueue_message(f"Reevaluating spot balance for {symbol}")
            next_so_val = self.__calculate_next_order_value(symbol, current_deal_orders)
            quote_asset = self.binance_client.get_quote_asset_from_symbol(symbol)
            self.assets_dataframe.upsert(symbol, next_so_val, quote_asset)
            if self.__is_rebalance_required(quote_asset):
                self.__rebalance_quote_assets([quote_asset])
            else:
                quote_asset = self.binance_client.get_quote_asset_from_symbol(symbol)
                self.send_savings_summary_msg(quote_asset, is_rebalanced=False)
        else:
            msg = f"Evaluated current deal orders but safety order is not yet open for {symbol}"
            logging.warn(msg)
            self.telegram_notifier.enqueue_message(msg)

    def __upsert_order_to_orders(self, order: Order, orders: List[Order]):
        """
        Sometimes when we fetch the list of orders from Binance it will return the new order related
        to the order event, other times the new order is missing from the list. To work around this
        we pass the "order event" order and only append it to the list if it wasn't returned in the
        call to Binance fetch all orders.
        """
        if order.get_deal_id() == orders[0].get_deal_id() and order.order_id not in [ord.order_id for ord in orders]:
            logging.info(
                f"Order {order.order_id} was not in list of orders. Appending order event to list. Order: {order}"
            )
            orders.append(order)
            return self.__sort_orders_by_timestamp(orders)
        return orders

    def __log_orders(self, orders: List[Order], label: str):
        logging.info(f"\n- -{label}: START ORDER LOGGING- -")
        for order in orders:
            logging.info(order)
        logging.info(f"- -{label}: END ORDER LOGGING- -\n")

    def __is_safety_order_open(self, current_deal_orders: List[Order]):
        """
        Ensures we have at least one Base Order (FILLED) and one open Safety Order (NEW)
        """
        statuses = [ord.status for ord in current_deal_orders]
        return "FILLED" in statuses and "NEW" in statuses

    def __is_rebalance_required(self, quote_asset: str):
        orders_sum = self.assets_dataframe.sum_next_orders(quote_asset)
        orders_max = self.assets_dataframe.max_next_orders(quote_asset)
        min_balance_required = max(orders_sum * self.quote_coverage, orders_max)
        current_spot_balance = self.binance_client.get_available_asset_balance(quote_asset)
        return current_spot_balance < min_balance_required

    # ---------------------------------------------------------------------------- #
    #                 Rebalance savings for one or all quote assets                #
    # ---------------------------------------------------------------------------- #

    def __rebalance_quote_assets(self, quote_asset=None):
        active_symbols = self.binance_client.get_symbols_by_client_order_id(self.order_id_regex)
        # When all safety orders are filled we do not want to count next orders in calculations, so we filter them out
        filtered_active_symbols = [x for x in active_symbols if all(y not in x for y in self.excluded_symbols)]
        quote_assets = self.__get_quote_assets(filtered_active_symbols) if quote_asset is None else set(quote_asset)
        self.telegram_notifier.enqueue_message("Reevaluating quote assets: {0}".format(", ".join(quote_assets)))
        for quote_asset in quote_assets:
            self.assets_dataframe.drop_by_quote_asset(quote_asset)
            quote_symbols = self.__filter_symbols_by_quote_asset(filtered_active_symbols, quote_asset)
            quote_precision = int(self.binance_client.get_quote_precision(quote_symbols[0]))
            for quote_symbol in quote_symbols:
                deal_orders = self.__get_current_deal_orders_by_symbol(quote_symbol)
                next_so = self.__calculate_next_order_value(quote_symbol, deal_orders)
                self.assets_dataframe.upsert(quote_symbol, next_so, quote_asset)
            current_quote_balance = self.binance_client.get_available_asset_balance(quote_asset)
            required_quote_balance = self.assets_dataframe.sum_next_orders(quote_asset)
            self.__rebalance_savings(quote_asset, quote_precision, current_quote_balance, required_quote_balance)

    def __get_quote_assets(self, active_symbols):
        return {self.binance_client.get_quote_asset_from_symbol(sym) for sym in active_symbols}

    def __filter_symbols_by_quote_asset(self, symbols, quote_asset):
        return [sym for sym in symbols if str(sym).endswith(quote_asset)]

    def __get_current_deal_orders_by_symbol(self, symbol: str) -> List[Order]:
        orders = self.binance_client.get_all_orders_by_symbol(symbol)
        filtered_orders = [ord for ord in orders if (ord.is_new_or_filled_order() and ord.is_buy_order())]
        sorted_filtered_orders = self.__sort_orders_by_timestamp(filtered_orders)
        # Extract the 3Commas deal ID from the client order ID
        deal_id = sorted_filtered_orders[0].get_deal_id()
        # Get all orders associated with the most recent deal
        return [ord for ord in sorted_filtered_orders if deal_id in ord.order_id]

    def __sort_orders_by_timestamp(self, orders: List[Order]) -> List[Order]:
        return sorted(orders, key=lambda x: x.timestamp, reverse=True)

    def __calculate_next_order_value(self, symbol: str, current_deal_orders: List[Order]) -> float:
        """
        Sometimes orders may change on Binance while this code is executing for another symbol.
        For example, if during reevaluation of a symbol another symbol also hits TP meaning its existing orders are cancelled.
        If this happens we will just use the current order size in current_deal_orders, or failing that return 0.0 for next order size.
        """
        open_so: Order = None
        try:
            open_so = [ord for ord in current_deal_orders if ord.is_new_order()][0]
        except IndexError as err:
            msg = f"Error occurred fetching orders for {symbol}. Most likely the symbol has hit take profit during this reevaluation. Correct calculation should happen on subsequent evaluation. See logs for more details."
            self.telegram_notifier.enqueue_message(msg)
            if len(current_deal_orders) > 0:
                open_so = current_deal_orders[0]
                logging.warn(
                    f"NEW order not available for {symbol}. Using order {open_so} to calculate next safety order instead. Error: {err}"
                )
            else:
                logging.error(
                    f"Unable to fetch any open orders for symbol {symbol}. Skipping safety order calculation and returning 0.0. Error: {err}"
                )
                return 0.0
        step_size = self.binance_client.get_symbol_step_size(symbol)
        next_so_cost = self.__calculate_next_so_cost(open_so, step_size)
        logging.info(f"Next safety order cost: {next_so_cost}")
        return next_so_cost

    def __calculate_next_so_cost(self, open_so: Order, step_size: float):
        step_size_buffer = float(open_so.price) * float(step_size)
        return float(open_so.quote_qty) * self.dca_volume_scale + step_size_buffer

    # ---------------------------------------------------------------------------- #
    #                           Preform rebalance savings                          #
    # ---------------------------------------------------------------------------- #

    def __rebalance_savings(self, quote_asset, quote_precision, current_quote_balance, required_quote_balance):
        rebalance_amount = round(current_quote_balance - required_quote_balance, quote_precision)
        if rebalance_amount < 0:
            rebalance_amount = abs(rebalance_amount)
            self.__redeem_asset_from_savings(quote_asset, rebalance_amount)
        elif rebalance_amount > 0:
            self.__subscribe_asset_to_savings(quote_asset, rebalance_amount)
        else:
            msg = "No rebalancing required"
            logging.info(msg)
            self.telegram_notifier.enqueue_message(msg)

    def __redeem_asset_from_savings(self, asset, quantity):
        """
        Move an amount of the asset from Flexible Savings to Spot Wallet
        """
        logging.info(f"Redeeming {quantity} {asset} to Spot Wallet")
        precision = self.asset_precision_calculator.get_asset_precision(asset)
        rounded_qty = f"%.{precision}f" % quantity

        # Notify user if we do not have enough in Flexible Savings to fund Spot Wallet requirements. In this case we will proceed to redeem all funds remaining
        savings_amount = self.binance_client.get_available_savings_by_asset(asset)
        if savings_amount < quantity:
            rounded_savings = f"%.{precision}f" % savings_amount
            msg = f"Not enough enough {asset} funds to cover upcoming Safety Orders. Moving all Flexible Savings to Spot Wallet. Required amount: {rounded_qty} {asset} Flexible Savings: {rounded_savings} {asset}"
            logging.warn(msg)
            self.telegram_notifier.enqueue_message(msg)
            quantity = savings_amount

        # Check if we can redeem from the asset, if not, add it as a failure for retrying later
        if not self.binance_client.can_redeem_savings_asset(asset):
            msg = f"{asset} is currently unavailable to redeem from Flexible Savings. Will retry when it becomes available"
            logging.warn(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.rebalance_failures.add(asset)
            return

        # Execute redemption from Flexible Savings
        try:
            if self.dry_run == False and quantity > 0:
                self.binance_client.redeem_from_savings(asset, quantity)
            else:
                msg = f"Running in dry-run mode. Will not move any funds"
                logging.info(msg)
                self.telegram_notifier.enqueue_message(msg)

            msg = f"Moved {rounded_qty} {asset} to Spot Wallet from Flexible Savings"
            logging.info(msg)
            self.telegram_notifier.enqueue_message(msg)
        except Exception as err:
            logging.exception(
                f"Exception occurred when attempting to rebalance savings for {asset}. Adding to failure set for retrying. Error: {err}"
            )
            self.telegram_notifier.enqueue_message(
                f"Error occurred when rebalancing asset {asset}. Will retry. See logs for details"
            )
            self.rebalance_failures.add(asset)

    def __subscribe_asset_to_savings(self, asset, quantity):
        """
        Move an amount of the asset from Spot Wallet to Flexible Savings
        """
        logging.info(f"Subscribing {quantity} {asset} to Flexible Savings")
        precision = self.asset_precision_calculator.get_asset_precision(asset)
        rounded_qty = f"%.{precision}f" % quantity

        # Ensure we are not attempting to subscribe less than the minimum allowed amount
        min_purchase_amount = self.binance_client.get_savings_min_purchase_amount_by_asset(asset)
        if quantity < min_purchase_amount:
            msg = f"{rounded_qty} {asset} is less than the minimum Flexible Savings purchase amount. Will not rebalance {asset} asset."
            logging.warn(msg)
            self.telegram_notifier.enqueue_message(msg)
            return

        # Check if we can subscribe to the asset, if not, add it as a failure for retrying later
        if not self.binance_client.can_purchase_savings_asset(asset):
            msg = f"{asset} is currently unavailable to purchase in Flexible Savings. Will retry when it becomes available"
            logging.warn(msg)
            self.telegram_notifier.enqueue_message(msg)
            self.rebalance_failures.add(asset)
            return

        # Execute subscription to Flexible Savings
        try:
            if self.dry_run == False:
                self.binance_client.subscribe_to_savings(asset, quantity)
            else:
                msg = f"Running in dry-run mode. Will not move any funds"
                logging.info(msg)
                self.telegram_notifier.enqueue_message(msg)
            msg = f"Moved {rounded_qty} {asset} from Spot Wallet to Flexible Savings"
            logging.info(msg)
            self.telegram_notifier.enqueue_message(msg)
        except Exception as err:
            logging.exception(
                f"Exception occurred when attempting to rebalance savings for {asset}. Adding to failure set for retrying. Error: {err}"
            )
            self.telegram_notifier.enqueue_message(
                f"Error occurred when rebalancing asset {asset}. Will attempt to retry. See logs for details"
            )
            self.rebalance_failures.add(asset)
