#!/usr/bin/env python

"""
Telegram bot to compliment a 3Commas DCA bot by maximising the amount of inactive quote asset earning interest in Binance Flexible Savings.

Usage:
Start bot using /start. This triggers a reevaluation of current savings and starts the Telegram bot and order websocket listener.
"""

import yaml
from binance_client import BinanceClient
from telegram_handler import TelegramHandler
from telegram_notifier import TelegramNotifier
from order_processor import OrderProcessor
from order_stream_reader import OrderStreamReader
from savings_evaluation import SavingsEvaluation


# Load config from .config.yml file
def load_conf_file(config_file):
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)
        telegram_config = config["telegram"]
        binance_config = config["binance"]
    return telegram_config, binance_config


telegram_config, binance_config = load_conf_file(".config.yml")


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
    return {
        ord["symbol"]
        for ord in client.get_open_orders()
        if "deal" in ord["clientOrderId"]
    }


def is_3commas_order(order_id):
    return "deal" in order_id


def main():
    telegram_notifier = TelegramNotifier(telegram_config["chat_id"])

    binance_client = BinanceClient(
        binance_config["api_key"], binance_config["secret_key"]
    )
    savings_evaluation = SavingsEvaluation(
        binance_config["order_id_regex"], binance_client, telegram_notifier
    )
    telegram_handler = TelegramHandler(
        telegram_config["api_key"], telegram_notifier, savings_evaluation
    )

    order_processor = OrderProcessor(
        binance_config["order_id_regex"],
        binance_client,
        savings_evaluation,
        telegram_notifier,
    )
    order_stream_reader = OrderStreamReader(
        binance_config["api_key"], binance_config["secret_key"], order_processor
    )
    order_stream_reader.start_order_stream()

    # Blocking call. Signals only work in main thread so this must final call from main
    telegram_handler.run_telegram_bot()

    # history = client.get_lending_interest_history(
    #     lendingType="DAILY",
    #     asset="USDT",
    #     startTime=1646524800000,
    #     endTime=1646539200000,
    # )
    # redeem = client.get_lending_redemption_history(lendingType="DAILY", asset="USDT")
    # purchase = client.get_lending_position(asset="USDT")
    # print(history)
    # print(redeem)
    # print(purchase)


if __name__ == "__main__":
    main()
