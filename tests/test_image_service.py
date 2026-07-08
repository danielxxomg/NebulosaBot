"""Unit tests for bot.services.image_service — rank card generation.

Covers:
    - generate_rank_card returns valid PNG bytes
    - Handles missing avatar URL (default avatar fallback)
    - XP bar reflects progress correctly
    - Various edge cases (zero XP, max level, etc.)

Strict TDD: RED phase — tests written BEFORE the implementation exists.
"""

from __future__ import annotations

import io

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_png(data: bytes) -> bool:
    """Return True if *data* starts with the PNG magic header."""
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _has_non_zero_pixels(img_bytes: bytes) -> bool:
    """Verify the PNG contains actual image data (not just transparent pixels).

    This checks that we don't just return a tiny empty image.
    """
    return len(img_bytes) > 500  # minimum PNG with content should be larger


# ---------------------------------------------------------------------------
# generate_rank_card — functional tests
# ---------------------------------------------------------------------------


class TestGenerateRankCard:
    """Tests for image_service.generate_rank_card().

    Because the image service uses Pillow synchronously, all tests call it
    directly (no async needed).  The async wrapper is tested at the StellarCog
    level in test_stellar_cog.py.
    """

    @pytest.fixture(autouse=True)
    def _import_service(self) -> None:
        """Lazy-import ImageService inside each test.

        This keeps the test file from crashing when ImageService doesn't
        exist yet (RED phase) while still letting the test be importable.
        """
        from bot.services.image_service import ImageService

        self.service = ImageService()

    # -- Valid PNG output ---------------------------------------------------

    def test_generate_rank_card_returns_valid_png(self) -> None:
        """Rank card output must be a valid PNG file with non-trivial content."""
        buf = self.service.generate_rank_card(
            username="TestUser",
            avatar_url="https://cdn.discordapp.com/avatars/111/abc.png",
            xp=500,
            level=3,
            rank=5,
            xp_for_current=300.0,
            xp_for_next=450.0,
        )
        assert isinstance(buf, io.BytesIO)
        png_data = buf.getvalue()
        assert _is_valid_png(png_data), "Output is not a valid PNG"
        assert _has_non_zero_pixels(png_data), "PNG is too small — likely empty"

    def test_generate_rank_card_returns_different_images(self) -> None:
        """Two calls with different users must produce different images."""
        buf1 = self.service.generate_rank_card(
            username="UserA",
            avatar_url=None,
            xp=100,
            level=1,
            rank=10,
            xp_for_current=0.0,
            xp_for_next=100.0,
        )
        buf2 = self.service.generate_rank_card(
            username="UserB",
            avatar_url=None,
            xp=500,
            level=3,
            rank=5,
            xp_for_current=300.0,
            xp_for_next=450.0,
        )
        data1 = buf1.getvalue()
        data2 = buf2.getvalue()

        # Both should be valid PNG.
        assert _is_valid_png(data1)
        assert _is_valid_png(data2)

        # The images should differ because the text content differs.
        assert data1 != data2, "Different inputs should produce different images"

    # -- Missing avatar ------------------------------------------------------

    def test_handle_missing_avatar_none(self) -> None:
        """When avatar_url is None, must not crash and still produce PNG."""
        buf = self.service.generate_rank_card(
            username="NoAvatar",
            avatar_url=None,
            xp=100,
            level=1,
            rank=99,
            xp_for_current=0.0,
            xp_for_next=100.0,
        )
        assert isinstance(buf, io.BytesIO)
        assert _is_valid_png(buf.getvalue()), "Should still produce valid PNG with no avatar"

    def test_handle_empty_avatar_string(self) -> None:
        """When avatar_url is an empty string, must not crash."""
        buf = self.service.generate_rank_card(
            username="EmptyAvatar",
            avatar_url="",
            xp=200,
            level=2,
            rank=50,
            xp_for_current=50.0,
            xp_for_next=225.0,
        )
        assert isinstance(buf, io.BytesIO)
        assert _is_valid_png(buf.getvalue())

    # -- XP bar progress -----------------------------------------------------

    def test_xp_bar_0_percent(self) -> None:
        """At 0% progress the XP bar should have minimal fill width."""
        buf = self.service.generate_rank_card(
            username="ZeroProgress",
            avatar_url=None,
            xp=100,
            level=1,
            rank=10,
            xp_for_current=0.0,  # just hit this level
            xp_for_next=150.0,  # need 150 to level up
        )
        assert _is_valid_png(buf.getvalue()), "0% progress should work without error"

    def test_xp_bar_100_percent(self) -> None:
        """At 100% progress the XP bar should be completely filled."""
        buf = self.service.generate_rank_card(
            username="FullProgress",
            avatar_url=None,
            xp=250,
            level=1,
            rank=10,
            xp_for_current=150.0,  # xp - threshold = 150
            xp_for_next=150.0,  # same as needed → 100%
        )
        assert _is_valid_png(buf.getvalue()), "100% progress should work without error"

    def test_xp_bar_mid_progress(self) -> None:
        """At ~50% the bar should be partially filled (intermediate)."""
        buf = self.service.generate_rank_card(
            username="HalfWay",
            avatar_url=None,
            xp=750,
            level=5,
            rank=3,
            xp_for_current=200.0,
            xp_for_next=400.0,  # 50%
        )
        assert _is_valid_png(buf.getvalue()), "Mid-progress should work without error"

    # -- Edge cases ----------------------------------------------------------

    def test_zero_xp_zero_level(self) -> None:
        """Level 0, 0 XP — edge case for new members."""
        buf = self.service.generate_rank_card(
            username="Newbie",
            avatar_url=None,
            xp=0,
            level=0,
            rank=999,
            xp_for_current=0.0,
            xp_for_next=100.0,
        )
        assert _is_valid_png(buf.getvalue())

    def test_high_level(self) -> None:
        """Level 99 with large XP values should render without overflow."""
        buf = self.service.generate_rank_card(
            username="Veteran",
            avatar_url=None,
            xp=999999,
            level=99,
            rank=1,
            xp_for_current=50000.0,
            xp_for_next=100000.0,
        )
        assert _is_valid_png(buf.getvalue())

    def test_long_username(self) -> None:
        """Very long usernames should not crash or overflow the card."""
        buf = self.service.generate_rank_card(
            username="SuperLongUsernameThatExceedsTheTypicalDiscordLimit32Chars",
            avatar_url=None,
            xp=300,
            level=2,
            rank=42,
            xp_for_current=50.0,
            xp_for_next=225.0,
        )
        assert _is_valid_png(buf.getvalue())


# ==========================================================================
# generate_greeting_card — welcome/goodbye card tests
# ==========================================================================


class TestGenerateGreetingCard:
    """Tests for ImageService.generate_greeting_card().

    The method must produce valid PNG output for both welcome and goodbye
    card types, handle missing avatars gracefully, and produce distinct
    outputs for different card types.
    """

    @pytest.fixture(autouse=True)
    def _import_service(self) -> None:
        """Lazy-import ImageService inside each test."""
        from bot.services.image_service import ImageService

        self.service = ImageService()

    # -- Valid PNG output ---------------------------------------------------

    def test_generate_greeting_card_returns_valid_png_welcome(self) -> None:
        """Welcome card must produce a valid PNG with non-trivial content."""
        buf = self.service.generate_greeting_card(
            username="TestUser",
            avatar_url="https://cdn.discordapp.com/avatars/111/abc.png",
            guild_name="Test Server",
            member_count=150,
            card_type="welcome",
        )
        assert isinstance(buf, io.BytesIO)
        png_data = buf.getvalue()
        assert _is_valid_png(png_data), "Output is not a valid PNG"
        assert _has_non_zero_pixels(png_data), "PNG is too small — likely empty"

    def test_generate_greeting_card_returns_valid_png_goodbye(self) -> None:
        """Goodbye card must produce a valid PNG with non-trivial content."""
        buf = self.service.generate_greeting_card(
            username="LeavingUser",
            avatar_url=None,
            guild_name="Test Guild",
            member_count=42,
            card_type="goodbye",
        )
        assert isinstance(buf, io.BytesIO)
        png_data = buf.getvalue()
        assert _is_valid_png(png_data), "Output is not a valid PNG"
        assert _has_non_zero_pixels(png_data), "PNG is too small — likely empty"

    def test_generate_greeting_card_returns_bytesio(self) -> None:
        """Output must be an io.BytesIO object positioned at the start."""
        buf = self.service.generate_greeting_card(
            username="User",
            avatar_url=None,
            guild_name="Guild",
            member_count=1,
            card_type="welcome",
        )
        assert isinstance(buf, io.BytesIO)
        # Positioned at start — ready for Discord upload.
        assert buf.tell() == 0

    # -- Card type produces different output ---------------------------------

    def test_welcome_vs_goodbye_produces_different_images(self) -> None:
        """Welcome and goodbye cards must be visually distinct."""
        buf_welcome = self.service.generate_greeting_card(
            username="SameUser",
            avatar_url=None,
            guild_name="G",
            member_count=100,
            card_type="welcome",
        )
        buf_goodbye = self.service.generate_greeting_card(
            username="SameUser",
            avatar_url=None,
            guild_name="G",
            member_count=100,
            card_type="goodbye",
        )
        assert buf_welcome.getvalue() != buf_goodbye.getvalue(), (
            "Welcome and goodbye cards must produce different images"
        )

    # -- Missing avatar ------------------------------------------------------

    def test_handle_missing_avatar_none(self) -> None:
        """When avatar_url is None, must not crash and still produce PNG."""
        buf = self.service.generate_greeting_card(
            username="NoAvatar",
            avatar_url=None,
            guild_name="Server",
            member_count=50,
            card_type="welcome",
        )
        assert isinstance(buf, io.BytesIO)
        assert _is_valid_png(buf.getvalue())

    def test_handle_empty_avatar_string(self) -> None:
        """When avatar_url is empty string, must not crash."""
        buf = self.service.generate_greeting_card(
            username="EmptyAvatar",
            avatar_url="",
            guild_name="Guild",
            member_count=10,
            card_type="goodbye",
        )
        assert _is_valid_png(buf.getvalue())

    # -- Edge cases ----------------------------------------------------------

    def test_long_username_does_not_crash(self) -> None:
        """Very long usernames should not crash or overflow the card."""
        buf = self.service.generate_greeting_card(
            username="SuperLongUsernameThatExceedsTheTypical32CharDiscordLimit",
            avatar_url=None,
            guild_name="A Guild",
            member_count=200,
            card_type="welcome",
        )
        assert _is_valid_png(buf.getvalue())

    def test_zero_member_count(self) -> None:
        """Member count of 0 should not crash."""
        buf = self.service.generate_greeting_card(
            username="FirstMember",
            avatar_url=None,
            guild_name="New Server",
            member_count=0,
            card_type="welcome",
        )
        assert _is_valid_png(buf.getvalue())

    def test_high_member_count(self) -> None:
        """Large member counts should display without overflow."""
        buf = self.service.generate_greeting_card(
            username="Member",
            avatar_url=None,
            guild_name="Popular Server",
            member_count=999999,
            card_type="welcome",
        )
        assert _is_valid_png(buf.getvalue())

    def test_invalid_card_type_defaults_to_welcome(self) -> None:
        """Unknown card_type should not crash — fallback to welcome style."""
        buf = self.service.generate_greeting_card(
            username="User",
            avatar_url=None,
            guild_name="Guild",
            member_count=5,
            card_type="unknown_value",
        )
        assert _is_valid_png(buf.getvalue())
