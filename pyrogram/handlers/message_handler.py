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
from .handler import Handler

if TYPE_CHECKING:
    from pyrogram import types


class MessageHandler(Handler):
    """The Message handler class. Used to handle new messages."""

    def __init__(self, callback: Callable[[pyrogram.Client, types.Message], Any], filters=None):
        self.original_callback = callback
        super().__init__(self.resolve_future_or_callback, filters)

    @staticmethod
    async def check_if_has_matching_listener(
        client: pyrogram.Client, message: types.Message
    ) -> tuple[bool, Listener | None]:
        from_user = message.from_user
        from_user_id = from_user.id if from_user else None
        from_user_username = from_user.username if from_user else None

        message_id = getattr(message, "id", getattr(message, "message_id", None))

        data = Identifier(
            message_id=message_id,
            chat_id=[message.chat.id, message.chat.username] if message.chat else None,
            from_user_id=[from_user_id, from_user_username],
        )

        listener = client.get_listener_matching_with_data(data, ListenerTypes.MESSAGE)
        listener_does_match = False

        if listener:
            filters = listener.filters
            if callable(filters):
                if inspect.iscoroutinefunction(filters.__call__):
                    listener_does_match = await filters(client, message)
                else:
                    listener_does_match = await client.loop.run_in_executor(
                        client.executor, filters, client, message
                    )
            else:
                listener_does_match = True

        return listener_does_match, listener

    async def check(self, client: pyrogram.Client, message: types.Message) -> bool:
        listener_does_match = (await self.check_if_has_matching_listener(client, message))[0]

        if callable(self.filters):
            if inspect.iscoroutinefunction(self.filters.__call__):
                handler_does_match = await self.filters(client, message)
            else:
                handler_does_match = await client.loop.run_in_executor(
                    client.executor, self.filters, client, message
                )
        else:
            handler_does_match = True

        return listener_does_match or handler_does_match

    async def resolve_future_or_callback(self, client: pyrogram.Client, message: types.Message, *args):
        listener_does_match, listener = await self.check_if_has_matching_listener(client, message)

        if listener and listener_does_match:
            client.remove_listener(listener)

            if listener.future and not listener.future.done():
                listener.future.set_result(message)
                raise pyrogram.StopPropagation
            if listener.callback:
                if inspect.iscoroutinefunction(listener.callback):
                    await listener.callback(client, message, *args)
                else:
                    listener.callback(client, message, *args)
                raise pyrogram.StopPropagation

            raise ValueError("Listener must have either a future or a callback")

        await self.original_callback(client, message, *args)
