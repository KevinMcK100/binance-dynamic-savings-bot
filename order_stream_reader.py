import logging, os, threading, time
from order_processor import OrderProcessor
from unicorn_binance_websocket_api import BinanceWebSocketApiManager


class OrderStreamReader:

    # Enable logging
    logging.basicConfig(
        level=logging.INFO,
        filename=os.path.basename(__file__) + ".log",
        format="{asctime} [{levelname:8}] {process} {thread} {module}: {message}",
        style="{",
    )
    logging.getLogger("unicorn_binance_websocket_api")

    def __init__(self, api_key, secret_key, order_processor: OrderProcessor):
        self.api_key = api_key
        self.secret_key = secret_key
        self.order_processor = order_processor

    def read_order_stream_buffer(self, binance_websocket_api_manager, order_stream):
        while True:
            if binance_websocket_api_manager.is_manager_stopping():
                exit(0)
            new_event = (
                binance_websocket_api_manager.pop_stream_data_from_stream_buffer(
                    order_stream
                )
            )
            if new_event is False:
                time.sleep(0.01)
            else:
                self.order_processor.process_order(new_event)

    def monitor_order_stream(self, binance_websocket_api_manager):
        while True:
            binance_websocket_api_manager.print_summary()
            time.sleep(5)

    def start_order_stream(self):
        ubwa = BinanceWebSocketApiManager(
            exchange="binance.com", output_default="UnicornFy"
        )
        # create the userData streams
        order_stream = ubwa.create_stream(
            "arr",
            "!userData",
            stream_label="3Commas",
            stream_buffer_name=True,
            api_key=self.api_key,
            api_secret=self.secret_key,
        )
        # start a worker process to move the received stream_data from the stream_buffer to a print function
        read_order_stream_worker = threading.Thread(
            target=self.read_order_stream_buffer, args=([ubwa, order_stream])
        )
        read_order_stream_worker.start()
        monitor_order_stream_worker = threading.Thread(
            target=self.monitor_order_stream, args=([ubwa])
        )
        monitor_order_stream_worker.start()
