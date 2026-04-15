import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.starts_onboarding import send_starts1_onboarding
from bot.handlers.user import cmd_start


class StartOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_cmd_start_uses_new_starts1_onboarding(self):
        user = SimpleNamespace(id=101, username="tester", full_name="Test User")
        message = SimpleNamespace(from_user=user)
        session = object()
        config = object()
        state = object()
        gspread_client = object()

        with (
            patch("bot.handlers.user.add_user", new=AsyncMock()),
            patch("bot.handlers.starts_onboarding.send_starts1_onboarding", new=AsyncMock()) as send_onboarding,
        ):
            await cmd_start(
                message=message,
                session=session,
                config=config,
                state=state,
                gspread_client=gspread_client,
            )

        send_onboarding.assert_awaited_once_with(
            message,
            session,
            config,
            gspread_client,
            source="/start",
        )

    async def test_send_starts1_onboarding_sends_video_before_analytics(self):
        events: list[str] = []
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=202),
            answer_video_note=AsyncMock(side_effect=lambda **kwargs: events.append("video_note")),
            answer=AsyncMock(side_effect=lambda *args, **kwargs: events.append("intro")),
        )

        async def report_side_effect(*args, **kwargs):
            events.append(kwargs["event_name"])

        with (
            patch("bot.handlers.starts_onboarding._sync_starts_onboarding_reporting", new=AsyncMock(side_effect=report_side_effect)),
            patch("bot.handlers.starts_onboarding.get_starts1_intro_keyboard", return_value=object()),
            patch("bot.handlers.starts_onboarding.asyncio.sleep", new=AsyncMock()),
        ):
            await send_starts1_onboarding(
                message=message,
                session=object(),
                config=object(),
            )

        self.assertEqual(
            events,
            ["video_note", "onboarding_started", "video_note_sent", "intro", "intro_sent"],
        )


if __name__ == "__main__":
    unittest.main()
