import logging, pytz
from apscheduler.schedulers.background import BackgroundScheduler
from balance_update import BalanceUpdate
from balance_update_processor import BalanceUpdateProcessor
from binance import ThreadedWebsocketManager
from order import Order
from order_update_processor import OrderUpdateProcessor


class WebsocketStreamReader:
    def __init__(
        self,
        api_key,
        secret_key,
        balance_update_processor: BalanceUpdateProcessor,
        order_processor: OrderUpdateProcessor,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.balance_update_processor = balance_update_processor
        self.order_processor = order_processor

    def start_order_stream(self):
        logging.info("Starting order stream reader")
        self.twm = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.secret_key)
        self.twm.start()
        self.twm.start_user_socket(callback=self.__handle_event)
        self.__do_health_check()

        # Start health check scheduler
        scheduler = BackgroundScheduler(timezone=pytz.utc)
        scheduler.add_job(self.__do_health_check, "interval", minutes=10)
        scheduler.start()

    def __handle_event(self, event):
        if event["e"] == "balanceUpdate":
            self.__handle_balance_update_event(event)
        elif event["e"] == "executionReport":
            self.__handle_order_update_event(event)

    def __handle_balance_update_event(self, balance_event):
        balance_update = self.__map_balance_update(balance_event)
        logging.info(f"Balance update event received: {balance_update}")
        self.balance_update_processor.process_balance_update(balance_update)

    def __handle_order_update_event(self, order_event):
        order = self.__map_order(order_event)
        logging.info(f"Order event received: {order}")
        self.order_processor.process_order(order)

    def __map_balance_update(self, balance_update: dict):
        return BalanceUpdate(balance_update["a"], balance_update["d"], balance_update["E"], balance_update["T"])

    def __map_order(self, order: dict):
        return Order(
            order["s"], float(order["p"]), float(order["q"]), order["c"], order["X"], order["S"], int(order["O"])
        )

    def __do_health_check(self):
        logging.info(f"ThreadedWebsocketManager health check: {self.twm.is_alive()}")
