import logging, pytz
from apscheduler.schedulers.background import BackgroundScheduler
from binance import ThreadedWebsocketManager
from order import Order
from order_processor import OrderProcessor


class OrderStreamReader:
    def __init__(self, api_key, secret_key, order_processor: OrderProcessor):
        self.api_key = api_key
        self.secret_key = secret_key
        self.order_processor = order_processor

    def start_order_stream(self):
        logging.info("Starting order stream reader")
        self.twm = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.secret_key)
        self.twm.start()
        self.twm.start_user_socket(callback=self.__handle_order_event)
        self.__do_health_check()

        # Start health check scheduler
        scheduler = BackgroundScheduler(timezone=pytz.utc)
        scheduler.add_job(self.__do_health_check, "interval", minutes=10)
        scheduler.start()

    def __handle_order_event(self, order_event):
        if order_event["e"] == "executionReport":
            order = self.__map_order(order_event)
            logging.info(f"Order event received: {order}")
            self.order_processor.process_order(order)

    def __map_order(self, order):
        return Order(
            order["s"], float(order["p"]), float(order["q"]), order["c"], order["X"], order["S"], int(order["O"])
        )

    def __do_health_check(self):
        logging.info(f"ThreadedWebsocketManager health check: {self.twm.is_alive()}")
