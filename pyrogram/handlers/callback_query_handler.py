#  Pyrogram - Telegram MTProto API Client Library for Python
#  Copyright (C) 2017-present Dan <https://github.com/delivrance>
#
#  This file is part of Pyrogram.
#
#  Pyrogram is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Pyrogram is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations as _annotations

import inspect
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

import pyrogram
from pyrogram.types.pyromod import Identifier, Listener, ListenerTypes
from pyrogram.utils import PyromodConfig
from .handler import Handler

if TYPE_CHECKING:
    from pyrogram import types


class CallbackQueryHandler(Handler):
    """The CallbackQuery handler class. Used to handle callback queries coming from inline buttons."""

    def __init__(
        self, callback: Callable[[pyrogram.Client, types.CallbackQuery], Any], filters=None
    ):
        self.original_callback = callback
        super().__init__(self.resolve_future_or_callback, filters)

    @staticmethod
    def compose_data_identifier(query: types.CallbackQuery) -> Identifier:
        from_user = query.from_user
        from_user_id = from_user.id if from_user else None
        from_user_username = from_user.username if from_user else None

        message = query.message
        message_id = getattr(message, "id", getattr(message, "message_id", None)) if message else None

        chat_id = None
        if message and message.chat:
            chat_id = [message.chat.id, message.chat.username]

        return Identifier(
            inline_message_id=query.inline_message_id,
            chat_id=chat_id,
            from_user_id=[from_user_id, from_user_username],
            message_id=message_id,
        )

    @classmethod
    async def check_if_has_matching_listener(
        cls, client: pyrogram.Client, query: types.CallbackQuery
    ) -> tuple[bool, Listener | None]:
        data = cls.compose_data_identifier(query)
        listener = client.get_listener_matching_with_data(data, ListenerTypes.CALLBACK_QUERY)
        listener_does_match = False

        if listener:
            filters = listener.filters
            if callable(filters):
                if inspect.iscoroutinefunction(filters.__call__):
                    listener_does_match = await filters(client, query)
                else:
                    listener_does_match = await client.loop.run_in_executor(
                        client.executor, filters, client, query
                    )
            else:
                listener_does_match = True

        return listener_does_match, listener

    async def check(self, client: pyrogram.Client, query: types.CallbackQuery) -> bool:
        listener_does_match, listener = await self.check_if_has_matching_listener(client, query)

        if callable(self.filters):
            if inspect.iscoroutinefunction(self.filters.__call__):
                handler_does_match = await self.filters(client, query)
            else:
                handler_does_match = await client.loop.run_in_executor(
                    client.executor, self.filters, client, query
                )
        else:
            handler_does_match = True

        data = self.compose_data_identifier(query)

        if PyromodConfig.unallowed_click_alert:
            permissive_identifier = Identifier(
                chat_id=data.chat_id,
                message_id=data.message_id,
                inline_message_id=data.inline_message_id,
                from_user_id=None,
            )

            matches = permissive_identifier.matches(data)

            if (
                listener
                and (matches and not listener_does_match)
                and listener.unallowed_click_alert
            ):
                alert = (
                    listener.unallowed_click_alert
                    if isinstance(listener.unallowed_click_alert, str)
                    else PyromodConfig.unallowed_click_alert_text
                )
                await query.answer(alert)

        return listener_does_match or handler_does_match

    async def resolve_future_or_callback(self, client: pyrogram.Client, query: types.CallbackQuery, *args):
        listener_does_match, listener = await self.check_if_has_matching_listener(client, query)

        if listener and listener_does_match:
            client.remove_listener(listener)

            if listener.future and not listener.future.done():
                listener.future.set_result(query)
                raise pyrogram.StopPropagation
            if listener.callback:
                if inspect.iscoroutinefunction(listener.callback):
                    await listener.callback(client, query, *args)
                else:
                    listener.callback(client, query, *args)
                raise pyrogram.StopPropagation

            raise ValueError("Listener must have either a future or a callback")

        await self.original_callback(client, query, *args)
