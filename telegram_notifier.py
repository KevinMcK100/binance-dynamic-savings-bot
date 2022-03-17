class TelegramNotifier:
    def __init__(self, chat_id):
        self.context = None
        self.chat_id = chat_id

    def initialise_notifier(self, context):
        """Notifier should be initialised upon starting the Telegram bot"""
        self.context = context

    def send_message(self, message):
        """Sends a message to Telegram based on chat ID of user or group."""
        if self.context is None or self.chat_id is None:
            print(f"Telegram bot not yet started. Couldn't send message: {message}")
        else:
            self.context.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
