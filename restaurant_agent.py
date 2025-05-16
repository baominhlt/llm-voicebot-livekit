from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Annotated, Optional, Union

import yaml
from dotenv import load_dotenv
from livekit.agents import JobContext, MetricsCollectedEvent, WorkerOptions, cli, metrics
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import silero
from pydantic import Field

from src.agent_models import AgentModel
from src.globals import logger

# from livekit.plugins import noise_cancellation


load_dotenv()

voices = {
    "greeter": "794f9389-aac1-45b6-b726-9d9369183238",
    "reservation": "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "takeaway": "6f84f4b8-58a2-430c-8c79-688dad597532",
    "checkout": "39b376fc-488e-4d0c-8b37-e00b72059fdd",
}


@dataclass
class UserData:
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None

    reservation_time: Optional[str] = None

    order: Optional[list[str]] = None

    customer_credit_card: Optional[str] = None
    customer_credit_card_expiry: Optional[str] = None
    customer_credit_card_cvv: Optional[str] = None

    expense: Optional[float] = None
    checked_out: Optional[bool] = None

    agents: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Optional[Agent] = None

    def summarize(self) -> str:
        data = {
            "customer_name": self.customer_name or "unknown",
            "customer_phone": self.customer_phone or "unknown",
            "reservation_time": self.reservation_time or "unknown",
            "order": self.order or "unknown",
            # "credit_card": {
            #     "number": self.customer_credit_card or "unknown",
            #     "expiry": self.customer_credit_card_expiry or "unknown",
            #     "cvv": self.customer_credit_card_cvv or "unknown",
            # }
            # if self.customer_credit_card
            # else None,
            "expense": self.expense or "unknown",
            "checked_out": self.checked_out or False,
        }
        # summarize in yaml performs better than json
        return yaml.dump(data)


RunContext_T = RunContext[UserData]


# common functions


@function_tool()
async def update_name(
    name: Annotated[str, Field(description="The customer's name")],
    context: RunContext_T,
) -> str:
    """Called when the user provides their name.
    Confirm the spelling with the user before calling the function."""
    userdata = context.userdata
    userdata.customer_name = name
    return f"The name is updated to {name}"


@function_tool()
async def update_phone(
    phone: Annotated[str, Field(description="The customer's phone number")],
    context: RunContext_T,
) -> str:
    """Called when the user provides their phone number.
    Confirm the spelling with the user before calling the function."""
    userdata = context.userdata
    userdata.customer_phone = phone
    return f"The phone number is updated to {phone}"


@function_tool()
async def to_greeter(context: RunContext_T) -> Agent:
    """Called when user asks any unrelated questions or requests
    any other services not in your job description."""
    curr_agent: BaseAgent = context.session.current_agent
    return await curr_agent._transfer_to_agent("greeter", context)


class BaseAgent(Agent):
    async def on_enter(self) -> None:
        agent_name = self.__class__.__name__
        logger.info(f"entering task {agent_name}")

        userdata: UserData = self.session.userdata
        chat_ctx = self.chat_ctx.copy()

        # add the previous agent's chat history to the current agent
        if isinstance(userdata.prev_agent, Agent):
            truncated_chat_ctx = userdata.prev_agent.chat_ctx.copy(
                exclude_instructions=True, exclude_function_call=False
            ).truncate(max_items=6)
            existing_ids = {item.id for item in chat_ctx.items}
            items_copy = [item for item in truncated_chat_ctx.items if item.id not in existing_ids]
            chat_ctx.items.extend(items_copy)

        # add an instructions including the user data as assistant message
        chat_ctx.add_message(
            role="system",  # role=system works for OpenAI's LLM and Realtime API
            content=f"Bạn là trợ lý tổng đài viên {agent_name}. Dữ liệu người dùng hiện tại là {userdata.summarize()}",
        )
        await self.update_chat_ctx(chat_ctx)
        self.session.generate_reply(tool_choice="none")

    async def _transfer_to_agent(self, name: str, context: RunContext_T) -> tuple[Agent, str]:
        userdata = context.userdata
        current_agent = context.session.current_agent
        next_agent = userdata.agents[name]
        userdata.prev_agent = current_agent

        return next_agent, f"Transferring to {name}."


class Greeter(BaseAgent):
    def __init__(self, menu: str) -> None:
        super().__init__(
            instructions=(
                f"Bạn là một nhân viên lễ tân nhà hàng thân thiện."
                "Nhiệm vụ của bạn là chào đón người gọi và hiểu xem họ có muốn "
                "đặt chỗ hay gọi đồ mang về không. Hướng dẫn họ đến đúng nhân viên bằng các công cụ."),
            llm=AgentModel.LLM,
            tts=AgentModel.TTS,
        )
        self.menu = menu

    # @function_tool()
    # async def to_reservation(self, context: RunContext_T) -> tuple[Agent, str]:
    #     """Called when user wants to make or update a reservation.
    #     This function handles transitioning to the reservation agent
    #     who will collect the necessary details like reservation time,
    #     customer name and phone number."""
    #     return await self._transfer_to_agent("reservation", context)

    @function_tool()
    async def to_takeaway(self, context: RunContext_T) -> tuple[Agent, str]:
        """Called when the user wants to place a takeaway order.
        This includes handling orders for pickup, delivery, or when the user wants to
        proceed to checkout with their existing order."""
        return await self._transfer_to_agent("takeaway", context)


class Reservation(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions="Bạn là nhân viên đặt chỗ tại một nhà hàng. Công việc của bạn là hỏi "
            "thời gian đặt chỗ, sau đó là tên khách hàng và số điện thoại. Sau đó "
            "xác nhận thông tin đặt chỗ với khách hàng.",
            tools=[update_name, update_phone, to_greeter],
            tts=AgentModel.TTS,
        )

    @function_tool()
    async def update_reservation_time(
        self,
        time: Annotated[str, Field(description="The reservation time")],
        context: RunContext_T,
    ) -> str:
        """Called when the user provides their reservation time.
        Confirm the time with the user before calling the function."""
        userdata = context.userdata
        userdata.reservation_time = time
        return f"The reservation time is updated to {time}"

    @function_tool()
    async def confirm_reservation(self, context: RunContext_T) -> Union[str, tuple[Agent, str]]:
        """Called when the user confirms the reservation."""
        userdata = context.userdata
        if not userdata.customer_name or not userdata.customer_phone:
            return "Please provide your name and phone number first."

        if not userdata.reservation_time:
            return "Please provide reservation time first."

        return await self._transfer_to_agent("greeter", context)


class Takeaway(BaseAgent):
    def __init__(self, menu: str) -> None:
        super().__init__(
            instructions=(
                f"Bạn là nhân viên bán đồ ăn mang về, tiếp nhận đơn hàng từ khách hàng "
                f"menu của nhà hàng như sau: {menu}. Chỉ hỏi khách hàng muốn gọi món gì và chốt tên món có trong menu, không chốt món không có trong menu"
                f"Làm rõ các yêu cầu đặc biệt và xác nhận đơn hàng với khách hàng."
                f"nếu khách hàng đọc món có sai sót, hãy hỏi lại khách hàng món gần giống nhất với món khách đọc"
            ),
            tools=[to_greeter],
            tts=AgentModel.TTS,
        )

    @function_tool()
    async def update_order(
        self,
        items: Annotated[list[str], Field(description="The items of the full order")],
        context: RunContext_T,
    ) -> str:
        """Called when the user create or update their order."""
        userdata = context.userdata
        userdata.order = items
        return f"The order is updated to {items}"

    @function_tool()
    async def to_checkout(self, context: RunContext_T) -> str | tuple[Agent, str]:
        """Called when the user confirms the order."""
        userdata = context.userdata
        if not userdata.order:
            return "No takeaway order found. Please make an order first."

        return await self._transfer_to_agent("checkout", context)


class Checkout(BaseAgent):
    def __init__(self, menu: str) -> None:
        super().__init__(
            instructions=(
                f"Bạn là nhân viên chốt đơn pizza tại nhà hàng. Thực đơn là: {menu}\n"
                "Bạn có trách nhiệm xác nhận chi phí của "
                "đơn hàng và sau đó thu thập tên, số điện thoại của khách hàng "
                "thu thập địa chỉ cụ thể của khách hàng, nếu địa chỉ không hợp lệ, hãy hỏi lại tên đường, quận, thành phố. "
                "Yêu cầu khách hàng đọc rõ đường gì, quận gì, thành phố gì và ghi nhận lại"
            ),
            tools=[update_name, update_phone, to_greeter],
            tts=AgentModel.TTS,
        )

    @function_tool()
    async def confirm_expense(
        self,
        expense: Annotated[float, Field(description="The expense of the order")],
        context: RunContext_T,
    ) -> str:
        """Called when the user confirms the expense."""
        userdata = context.userdata
        userdata.expense = expense
        return f"The expense is confirmed to be {expense}"

    # @function_tool()
    # async def update_credit_card(
    #     self,
    #     number: Annotated[str, Field(description="The credit card number")],
    #     expiry: Annotated[str, Field(description="The expiry date of the credit card")],
    #     cvv: Annotated[str, Field(description="The CVV of the credit card")],
    #     context: RunContext_T,
    # ) -> str:
    #     """Called when the user provides their credit card number, expiry date, and CVV.
    #     Confirm the spelling with the user before calling the function."""
    #     userdata = context.userdata
    #     userdata.customer_credit_card = number
    #     userdata.customer_credit_card_expiry = expiry
    #     userdata.customer_credit_card_cvv = cvv
    #     return f"The credit card number is updated to {number}"
    @function_tool()
    async def update_address(
        self,
        address: Annotated[str, Field(description="The address of the customer")],
        context: RunContext_T,
    ) -> str:
        """Called when the user provides their address.
        Confirm the spelling with the user before calling the function."""
        userdata = context.userdata
        userdata.customer_address = address
        return f"The address is updated to {address}"

    # @function_tool()
    # async def confirm_checkout(self, context: RunContext_T) -> str | tuple[Agent, str]:
    #     """Called when the user confirms the checkout."""
    #     userdata = context.userdata
    #     if not userdata.expense:
    #         return "Please confirm the expense first."

    #     if (
    #         not userdata.customer_credit_card
    #         or not userdata.customer_credit_card_expiry
    #         or not userdata.customer_credit_card_cvv
    #     ):
    #         return "Please provide the credit card information first."

    #     userdata.checked_out = True
    #     return await to_greeter(context)

    @function_tool()
    async def to_takeaway(self, context: RunContext_T) -> tuple[Agent, str]:
        """Called when the user wants to update their order."""
        return await self._transfer_to_agent("takeaway", context)


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    MENU = [
        "Nui Bỏ Lò Phô Mai Gà Bơ Tỏi và Nấm Sốt Kem: 100000",
        "Nui Bỏ Lò Phô Mai Rau Củ Sốt Kem: 100000",
        "Mỳ Ý Truffle: 100000",
        "Mì Ý Pesto: 100000",
        "Mỳ Ý Cay Hải Sản: 100000",
        "Mỳ Ý Chay Sốt Marinara: 100000",
        "Mỳ Ý Tôm Sốt Kem Cà Chua: 100000",
        "Mỳ Ý Cay Xúc Xích: 100000",
        "Mỳ Ý Giăm Bông Và Nấm Sốt Kem: 100000",
        "Mỳ Ý thịt bò bằm: 100000",
        "Mỳ Ý Chay Sốt Kem Tươi: 100000",
        "Mỳ Ý Nghêu Xốt Húng Quế: 100000",
        "Mỳ Ý Nghêu Xốt Cay: 100000",
        "Salad Trái Cây Sốt Đào: 100000",
        "Salad Trộn Dầu Giấm: 100000",
        "Salad Nui: 100000",
        "Salad Đặc Sắc: 100000",
        "Salad Gà Giòn Không Xương: 100000",
        "Salad Da Cá Hồi Giòn: 100000",
        "Salad Trộn Sốt Caesar: 100000",
        "Salad Bắp Cải: 100000",
        "Pepsi Lon: 100000",
    ]
    menu = " ".join(MENU)
    userdata = UserData()
    userdata.agents.update(
        {
            "greeter": Greeter(menu),
            "reservation": Reservation(),
            "takeaway": Takeaway(menu),
            "checkout": Checkout(menu),
        }
    )

    logger.info(f"BEGIN NEW SESSION AT {datetime.datetime.now()}")

    session = AgentSession[UserData](
        userdata=userdata,
        stt=AgentModel.STT,
        llm=AgentModel.LLM,
        tts=AgentModel.TTS,
        vad=silero.VAD.load(),
        max_tool_steps=5,
        turn_detection="vad",
        # to use realtime model, replace the stt, llm, tts and vad with the following
        # llm=openai.realtime.RealtimeModel(voice="alloy"),
    )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"History: {session._chat_ctx}")
        logger.info(f"Usage: {summary}")

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=userdata.agents["takeaway"],
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # await agent.say("Welcome to our restaurant! How may I assist you today?")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
