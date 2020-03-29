# -*- coding: utf-8 -*-

import deltachat as dc
from deltachat import account_hookimpl
from deltachat.tracker import ConfigureTracker

from .commands import Commands
from .filters import Filters
from .plugins import Plugins


class Filter():
    def __call__(self, msg):
        return False


class DeltaBot:
    def __init__(self, account, logger):
        self.account = account

        self.logger = logger

        #: plugin subsystem for adding/removing plugins and calling plugin hooks
        self.plugins = Plugins(bot=self)

        #: commands subsystem for registering/executing '/*' commands in incoming messages
        self.commands = Commands(self)

        #: filter subsystem for registering/performing filters on incoming messages
        self.filters = Filters(self)

        # set some useful bot defaults
        self.account.update_config(dict(
            save_mime_headers=1,
            e2ee_enabled=1,
            sentbox_watch=0,
            mvbox_watch=0,
            bcc_self=0
        ))
        self.account.add_account_plugin(self)
        self.plugins.hook.deltabot_configure.call_historic(kwargs=dict(bot=self))

    def is_configured(self):
        return bool(self.account.is_configured())

    def configure(self, email, password):
        with self.account.temp_plugin(ConfigureTracker()) as configtracker:
            self.account.update_config(dict(addr=email, mail_pw=password))
            self.account.start()
            try:
                configtracker.wait_finish()
            except configtracker.ConfigureFailed:
                self.logger.error('Bot configuration failed')
            else:
                self.logger.info('Bot configured successfully!')
            self.account.shutdown()

    def get_blobdir(self):
        return self.account.get_blobdir()

    def set_name(self, name):
        self.account.set_config('displayname', name)

    def send_file(self, chat, path, text, view_type='file'):
        msg = dc.message.Message.new_empty(self.account, view_type)
        msg.set_file(path)
        msg.set_text(text)
        chat.send_msg(msg)

    def on_message_delivered(self, msg):
        pass

    def start(self):
        addr = self.account.get_config("addr")
        self.logger.info("bot connected at: {}".format(addr))
        self.account.start()

    def wait_shutdown(self):
        self.account.wait_shutdown()

    @account_hookimpl
    def ac_incoming_message(self, message):
        try:
            # we always accept incoming messages to remove the need
            # for bot authors to having to deal with deaddrop/contact
            # request.  But we record whether it was one in case
            # a bot author still wants to act on it. This way it's still possible
            # to block or ignore an original contact request
            message.was_contact_request = message.chat.is_deaddrop()
            message.accept_sender_contact()
            self.logger.info("incoming message from {} id={} chat={} text={!r}".format(
                message.get_sender_contact().addr,
                message.id, message.chat.id, message.text[:50]))

            # If this is a "/" command we don't apply filters.
            reply = self.commands.process_command_message(message)
            if reply:
                self.send_reply(reply)
            else:
                for reply in self.filters.process_incoming(message):
                    self.send_reply(reply)

        except Exception as ex:
            self.logger.exception(ex)

    def send_reply(self, reply):
        msg = reply.chat.send_msg(reply.msg)
        self.logger.info("reply id={} chat={} sent with text: {!r}".format(
            msg.id, msg.chat, msg.text[:50]
        ))

    @account_hookimpl
    def ac_process_message_delivered(self, message):
        try:
            self.on_message_delivered(message)
        except Exception as ex:
            self.logger.exception(ex)

    def get_contact(self, addr=None):
        if addr is None:
            return self.account.get_self_contact()
        else:
            return self.account.create_contact(addr.strip())

    def get_chat(self, ref):
        if type(ref) is dc.message.Message:
            return self.account.create_chat_by_message(ref)
        elif type(ref) is dc.contact.Contact:
            return self.account.create_chat_by_contact(ref)
        elif type(ref) is str and '@' in ref:
            c = self.account.create_contact(ref.strip())
            return self.account.create_chat_by_contact(c)
        elif type(ref) is int:
            try:
                return self.account.get_chat_by_id(ref)
            except ValueError:
                return None

    def get_chats(self):
        return self.account.get_chats()

    def get_address(self):
        return self.get_contact().addr

    def create_group(self, name, members=[]):
        group = self.account.create_group_chat(name)
        for member in members:
            if type(member) is str:
                member = self.account.create_contact(member.strip())
            group.add_contact(member)
        return group

    def is_group(self, chat):
        return chat.is_group()