import logging

from collections import deque
from threading import Thread
from time import sleep
from telegram.error import RetryAfter


class TelegramNotifier:
    """
    Client to handle sending messages to a Telegram group.

    As per Telegram API docs, we should not send more than one message in any one second
    or more than 20 messages in any one minute otherwise we will be rate limited.

    We are using a combination of queues and with exception handling to address these requirements.

    https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this
    """

    def __init__(self, chat_id: str, verbose: bool = False):
        self.chat_id = chat_id
        self.verbose = verbose
        self.context = None
        self.message_queue = deque()

    def start_notifier(self, context):
        """
        Sets the context and starts polling the queue for messages to send to Telegram.
        """
        self.context = context
        message_queue_worker = Thread(target=self.__read_message_queue, name="TelegramNotifierThread")
        message_queue_worker.start()

    def enqueue_message(self, message: str, is_verbose: bool = False):
        """
        Enqueues a message to be picked by the worker thread and sent to Telegram group
        """
        self.message_queue.append((message, is_verbose))

    def __read_message_queue(self):
        """
        Polls the queue for new messages to be sent to Telegram group.

        Here we read from the queue at 1 second intervals.

        This achieves the first rate limiting constraint:
        "avoid sending more than one message per second"
        """
        while True:
            if len(self.message_queue) > 0:
                self.__send_message(self.message_queue.popleft())
            sleep(1)

    def __send_message(self, queue_item: tuple):
        """
        Sends a message to Telegram group

        Here we catch any RetryAfter exceptions and sleep the thread for the given duration.
        Failed messages will placed on the front of the queue for retrying.

        This addresses the second rate limiting constraint:
        "your bot will not be able to send more than 20 messages per minute to the same group"
        """
        message = queue_item[0]
        is_verbose = queue_item[1]
        if self.context is None or self.chat_id is None:
            logging.error(f"Telegram bot not yet started. Couldn't send message: {message}")
        elif self.verbose == True or is_verbose == False:
            try:
                self.context.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
            except RetryAfter as retry_ex:
                retry_after = retry_ex.retry_after
                logging.warn(f"Received rate limit error. Retrying after {retry_after} seconds.")
                self.message_queue.appendleft(queue_item)
                sleep(retry_after)
            except Exception as telegram_ex:
                logging.exception(
                    f"Unexpected exception sending message to Telegram. Will not retry sending message. Error: {telegram_ex}"
                )
