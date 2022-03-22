from binance import ThreadedWebsocketManager
from datetime import timedelta
from order_processor import OrderProcessor
from scheduler import Scheduler
from threading import Thread
from time import sleep


class OrderStreamReader:
    def __init__(self, api_key, secret_key, order_processor: OrderProcessor):
        self.api_key = api_key
        self.secret_key = secret_key
        self.order_processor = order_processor

    def start_order_stream(self):
        print("Starting order stream reader")
        self.twm = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.secret_key)
        self.twm.start()
        self.twm.start_user_socket(callback=self.__handle_order_event)
        self.__do_health_check()

        monitor_worker = Thread(target=self.__start_monitoring)
        monitor_worker.start()

    def __handle_order_event(self, order_event):
        if order_event["e"] == "executionReport":
            order = self.__map_order(order_event)
            self.order_processor.process_order(order)

    def __map_order(self, order):
        return {
            "symbol": order["s"],
            "order_id": order["c"],
            "side": order["S"],
            "quantity": order["q"],
            "price": order["p"],
            "status": order["X"],
        }

    def __start_monitoring(self):
        schedule = Scheduler()
        schedule.cyclic(timedelta(minutes=10), self.__do_health_check)
        while True:
            schedule.exec_jobs()
            sleep(1)

    def __do_health_check(self):
        print(f"ThreadedWebsocketManager health check: {self.twm.is_alive()}")
