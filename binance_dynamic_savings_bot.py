#!/usr/bin/env python

"""
Telegram bot to compliment a 3Commas DCA bot by maximising the amount of inactive quote asset earning interest in Binance Flexible Savings.

Usage:
Start bot using /start. This triggers a reevaluation of current savings and starts the Telegram bot and order websocket listener.
"""

import yaml
from assets_dataframe import AssetsDataframe
from binance_client import BinanceClient
from failure_handler import FailureHandler
from telegram_handler import TelegramHandler
from telegram_notifier import TelegramNotifier
from order_processor import OrderProcessor
from order_stream_reader import OrderStreamReader
from rebalance_savings_scheduler import RebalanceSavingsScheduler
from savings_evaluation import SavingsEvaluation


# Load config from .config.yml file
def load_conf_file(config_file):
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)
        telegram_config = config["telegram"]
        binance_config = config["binance"]
        dca_bot_config = config["dca_bot"]
    return telegram_config, binance_config, dca_bot_config


telegram_config, binance_config, dca_bot_config = load_conf_file(".config.yml")


def is_open_so_set(current_deal_orders):
    # Ensures we have at least one Base Order (FILLED) and one open Safety Order (NEW)
    return len(set([ord["status"] for ord in current_deal_orders])) == 2


def calculate_next_so_cost(open_so, step_size):
    step_size_buffer = float(open_so["price"]) * float(step_size)
    return float(open_so["quote_qty"]) * 1.05 + step_size_buffer


def get_symbol_step_size(client, symbol):
    return client.get_symbol_info(symbol=symbol)["filters"][2]["stepSize"]


def filter_orders(orders, statuses, sides):
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


def on_take_profit(client, symbol, con):

    # step_size = get_symbol_step_size(client, symbol)
    # orders = client.get_all_orders(symbol=symbol)
    # filtered_orders = filter_orders(orders, ["FILLED", "NEW"], ["BUY", "SELL"])
    # filtered_orders.sort(key=lambda x: x.get("timestamp"), reverse=True)
    # tp_order = [
    #     ord
    #     for ord in filtered_orders
    #     if ord["status"] == "FILLED" and ord["side"] == "SELL"
    # ][0]
    # cur = con.cursor()
    # cur.execute(
    #     "INSERT INTO take_profits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    #     (
    #         symbol,
    #         tp_order["price"],
    #         tp_order["quote_qty"],
    #         tp_order["qty"],
    #         tp_order["order_id"],
    #         tp_order["timestamp"],
    #         tp_order["status"],
    #         tp_order["side"],
    #         False,
    #     ),
    # )
    # con.commit()
    # print(tp_order)
    # # for order in filtered_orders:
    # #     print(order)
    print("to be implemented with cache")


def get_active_3c_symbols(client):
    return {ord["symbol"] for ord in client.get_open_orders() if "deal" in ord["clientOrderId"]}


def is_3commas_order(order_id):
    return "deal" in order_id


def main():
    telegram_notifier = TelegramNotifier(telegram_config["chat_id"])

    binance_client = BinanceClient(binance_config["api_key"], binance_config["secret_key"])
    assets_dataframe = AssetsDataframe()
    savings_evaluation = SavingsEvaluation(
        dca_bot_config["order_id_regex"],
        binance_client,
        telegram_notifier,
        dca_bot_config["dca_volume_scale"],
        assets_dataframe,
    )

    FailureHandler(binance_client, savings_evaluation, telegram_notifier)

    schedule_hour, schedule_min = dca_bot_config["rebalance_time"]["hour"], dca_bot_config["rebalance_time"]["minute"]
    rebalance_savings_scheduler = RebalanceSavingsScheduler(savings_evaluation, schedule_hour, schedule_min)
    telegram_handler = TelegramHandler(
        telegram_config["api_key"], telegram_notifier, savings_evaluation, rebalance_savings_scheduler
    )

    order_processor = OrderProcessor(
        dca_bot_config["order_id_regex"], binance_client, savings_evaluation, telegram_notifier
    )
    order_stream_reader = OrderStreamReader(binance_config["api_key"], binance_config["secret_key"], order_processor)
    order_stream_reader.start_order_stream()

    # Blocking call. Signals only work in main thread so this must final call from main
    telegram_handler.run_telegram_bot()


if __name__ == "__main__":
    main()
