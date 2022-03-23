#!/usr/bin/env python

"""
Telegram bot to compliment a 3Commas DCA bot by maximising the amount of inactive quote asset earning interest in Binance Flexible Savings.

Usage:
Start bot using /start. This triggers a reevaluation of current savings and starts the Telegram bot and order websocket listener.
"""

import logging, os, yaml
from assets_dataframe import AssetsDataframe
from binance_client import BinanceClient
from failure_handler import FailureHandler
from order_processor import OrderProcessor
from order_stream_reader import OrderStreamReader
from rebalance_savings_scheduler import RebalanceSavingsScheduler
from savings_evaluation import SavingsEvaluation
from telegram_handler import TelegramHandler
from telegram_notifier import TelegramNotifier

# Enable logging
logging.basicConfig(
    level=logging.INFO,
    filename=os.path.basename(__file__) + ".log",
    format="{asctime} [{levelname:8}] {process} {thread} {module}: {message}",
    style="{",
)

# Load config from .config.yml file
def load_conf_file(config_file):
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)
        telegram_config = config["telegram"]
        binance_config = config["binance"]
        dca_bot_config = config["dca_bot"]
    return telegram_config, binance_config, dca_bot_config


telegram_config, binance_config, dca_bot_config = load_conf_file(".config.yml")


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
    rebalance_savings_scheduler = RebalanceSavingsScheduler(
        savings_evaluation, telegram_notifier, schedule_hour, schedule_min
    )
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
