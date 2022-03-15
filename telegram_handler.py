from telegram.ext import Updater, CommandHandler
from telegram_notifier import TelegramNotifier
from savings_evaluation import SavingsEvaluation


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

    def start_telegram_bot(self, api_key):
        # """Initialise Telegram bot."""
        self.updater = Updater(api_key, use_context=True)

        # Add command handlers
        dp = self.updater.dispatcher
        dp.add_handler(CommandHandler("start", self.__start))  # /start

        # Start the Telegram Bot
        self.updater.start_polling()

    def run_telegram_bot(self):
        """
        Blocking call. Signals only work in main thread so this must be the final call called in from main after setup is complete
        """
        self.updater.idle()

    def __start(self, update, context):
        """Starts the bot. Executes on /start command"""
        self.telegram_notifier.initialise_notifier(context)
        self.telegram_notifier.send_message("Starting Binance Dynamic Savings Bot...")
        self.savings_evaluation.reevaluate_all_symbols()
