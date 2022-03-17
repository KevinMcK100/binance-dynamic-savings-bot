import threading
from typing import final
from telegram.ext import Updater, CommandHandler
from telegram_notifier import TelegramNotifier
from savings_evaluation import SavingsEvaluation
from time import sleep


class TelegramHandler:
    def __init__(
        self,
        api_key,
        telegram_notifier: TelegramNotifier,
        savings_evaluation: SavingsEvaluation,
    ):
        self.telegram_notifier = telegram_notifier
        self.savings_evaluation = savings_evaluation
        self.start_telegram_bot(api_key)
        self.bot_started = False

    def start_telegram_bot(self, api_key):
        # """Initialise Telegram bot."""
        self.updater = Updater(
            api_key,
            use_context=True,
            request_kwargs={"connect_timeout": 10, "read_timeout": 20},
        )

        # Add command handlers
        dp = self.updater.dispatcher
        dp.add_handler(CommandHandler("start", self.__start))  # /start
        dp.add_handler(CommandHandler("reevaluate", self.__reevaluate))  # /reevaluate
        dp.add_handler(CommandHandler("fail", self.__fail))  # /fail

        # Start the Telegram Bot
        self.updater.start_polling()

    def run_telegram_bot(self):
        """
        Blocking call. Signals only work in main thread so this must be the final call called in from main after setup is complete
        """
        self.updater.idle()

    def __start(self, update, context):
        """Starts the bot. Executes on /start command"""
        if not self.bot_started:
            self.telegram_notifier.initialise_notifier(context)
            self.telegram_notifier.send_message("Starting Binance Dynamic Savings Bot...")
            # self.savings_evaluation.reevaluate_all_symbols()
            self.bot_started = True
        else:
            self.telegram_notifier.send_message("Bot is already started. Execute /help for more commands")

    def __reevaluate(self, update, context):
        """Reevaluates all assets and redistributes quote assets between Flexible Savings and Spot Wallet. Executes on /reevaluate command"""
        if self.bot_started:
            self.telegram_notifier.send_message("Reevaluating quote assets...")
            self.savings_evaluation.reevaluate_all_symbols()
        else:
            print("Bot is not started. Execute /start command from Telegram")

    def __fail(self, update, context):
        print("Faking failure")
        self.savings_evaluation.rebalance_failures = {"USDT", "BTC"}
