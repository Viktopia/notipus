"""Tests for message generator style and tone.

This module tests that generated messages maintain the brand voice
with appropriate emojis, celebratory phrases, and conversational tone.

Tests use mocked random.choice to ensure deterministic template selection.
"""

from typing import Any
from unittest.mock import patch

import pytest
from webhooks.message_generator import MessageGenerator


@pytest.fixture
def generator() -> MessageGenerator:
    """Create a MessageGenerator instance for tests."""
    return MessageGenerator()


class TestPaymentSuccessMessages:
    """Tests for payment success message generation."""

    def test_all_templates_are_celebratory(self, generator: MessageGenerator) -> None:
        """Test that all payment success templates have celebratory tone.

        Iterates through all templates to ensure each one passes the style check.
        """
        event = {"customer_name": "Acme Corp", "amount": "$500", "plan": "Pro"}
        success_emojis = ["🎉", "💸", "🎊", "🚀", "💪", "🙌", "💥", "👀", "🏆", "🔐"]
        celebratory_phrases = [
            "Woohoo",
            "Awesome",
            "Yay",
            "Sweet",
            "Nice one",
            "Ka-ching",
            "High five",
            "Boom",
            "Look at that",
            "Winner winner",
            "vault",
        ]

        for template in generator.PAYMENT_SUCCESS_TEMPLATES:
            message = template.format(**event)
            assert any(
                emoji in message for emoji in success_emojis
            ), f"Template missing emoji: {template}"
            assert any(
                phrase in message for phrase in celebratory_phrases
            ), f"Template missing celebratory phrase: {template}"
            assert event["customer_name"] in message
            assert event["amount"] in message

    def test_payment_success_with_specific_template(
        self, generator: MessageGenerator
    ) -> None:
        """Test payment_success method with mocked template selection."""
        event = {"customer_name": "Acme Corp", "amount": "$500"}

        # Use the first template for deterministic testing
        with patch("webhooks.message_generator.random.choice") as mock_choice:
            mock_choice.return_value = generator.PAYMENT_SUCCESS_TEMPLATES[0]
            message = generator.payment_success(event)

        assert "Acme Corp" in message
        assert "$500" in message
        assert "🎉" in message  # First template uses this emoji


class TestPaymentFailureMessages:
    """Tests for payment failure message generation."""

    def test_all_templates_are_light_but_clear(
        self, generator: MessageGenerator
    ) -> None:
        """Test that all payment failure templates maintain humor while being clear."""
        event = {
            "customer_name": "Acme Corp",
            "amount": "$500",
            "reason": "card_expired",
        }
        failure_emojis = ["😅", "🤔", "👀", "💭", "👋", "🚧", "📢", "📞", "🔔"]
        light_phrases = [
            "Oops",
            "Uh-oh",
            "Looks like",
            "Seems like",
            "Hit a snag",
            "Friendly nudge",
            "Hey team",
            "Attention needed",
            "Time to reach out",
            "Just a heads up",
            "Heads up",
            "FYI",
        ]
        action_phrases = [
            "needs attention",
            "needs looking at",
            "could use",
            "speed bump",
            "didn't quite land",
            "needs some tlc",
            "waiting for a retry",
        ]

        for template in generator.PAYMENT_FAILURE_TEMPLATES:
            message = template.format(**event)
            lower_message = message.lower()
            assert any(
                emoji in message for emoji in failure_emojis
            ), f"Template missing emoji: {template}"
            assert any(
                phrase in message for phrase in light_phrases
            ), f"Template missing light phrase: {template}"
            assert any(
                phrase in lower_message for phrase in action_phrases
            ), f"Template missing action phrase: {template}"

    def test_payment_failure_with_specific_template(
        self, generator: MessageGenerator
    ) -> None:
        """Test payment_failure method with mocked template selection."""
        event = {"customer_name": "Acme Corp", "amount": "$500"}

        with patch("webhooks.message_generator.random.choice") as mock_choice:
            mock_choice.return_value = generator.PAYMENT_FAILURE_TEMPLATES[0]
            message = generator.payment_failure(event)

        assert "Acme Corp" in message
        assert "😅" in message  # First template uses this emoji


class TestTrialEndingMessages:
    """Tests for trial ending message generation."""

    def test_all_templates_are_encouraging(self, generator: MessageGenerator) -> None:
        """Test that all trial ending templates are encouraging and positive."""
        event = {
            "customer_name": "Acme Corp",
            "trial_usage": "high",
            "popular_features": "API and Dashboard",  # Pre-formatted for template
        }
        trial_emojis = ["✨", "🌟", "💫", "🚀", "🎯", "⏳", "🎁", "⏰", "🔍"]
        encouraging_phrases = [
            "loving",
            "crushing it",
            "rocking",
            "making the most of",
            "really getting into",
            "trial adventure",
            "trial countdown",
            "tick tock",
            "exploring",  # "exploring ... like a pro" has text in between
        ]

        for template in generator.TRIAL_ENDING_TEMPLATES:
            message = template.format(**event)
            lower_message = message.lower()
            assert any(
                emoji in message for emoji in trial_emojis
            ), f"Template missing emoji: {template}"
            assert any(
                phrase in lower_message for phrase in encouraging_phrases
            ), f"Template missing encouraging phrase: {template}"

    def test_trial_ending_with_specific_template(
        self, generator: MessageGenerator
    ) -> None:
        """Test trial_ending method with mocked template selection."""
        event = {
            "customer_name": "Acme Corp",
            "popular_features": ["API", "Dashboard"],
        }

        with patch("webhooks.message_generator.random.choice") as mock_choice:
            mock_choice.return_value = generator.TRIAL_ENDING_TEMPLATES[0]
            message = generator.trial_ending(event)

        assert "Acme Corp" in message
        assert "✨" in message  # First template uses this emoji
        # Features should be formatted
        assert "API" in message or "Dashboard" in message


class TestUpgradeMessages:
    """Tests for plan upgrade message generation."""

    def test_all_templates_are_extra_celebratory(
        self, generator: MessageGenerator
    ) -> None:
        """Test that all upgrade templates are extra enthusiastic."""
        event = {
            "customer_name": "Acme Corp",
            "old_plan": "Basic",
            "new_plan": "Pro",
            "team_size": 10,
        }
        upgrade_emojis = ["🎉", "🚀", "⭐️", "🌟", "💪", "💥", "🔓", "📈", "🎯", "🌠"]
        enthusiastic_phrases = [
            "Awesome upgrade",
            "Leveled up",
            "Power up",
            "Supercharged",
            "Next level",
            "Boom",
            "Growth mode",
            "scaling up",
            "Big moves",
            "sky's the limit",
        ]
        growth_phrases = [
            "growing",
            "scaling",
            "expanding",
            "moving up",
            "bigger",
            "unlocked",
            "upgraded",
        ]

        for template in generator.UPGRADE_TEMPLATES:
            message = template.format(**event)
            lower_message = message.lower()

            emoji_count = sum(message.count(emoji) for emoji in upgrade_emojis)
            assert emoji_count >= 2, f"Template needs more emojis: {template}"

            assert any(
                phrase in message for phrase in enthusiastic_phrases
            ), f"Template missing enthusiastic phrase: {template}"
            assert any(
                phrase in lower_message for phrase in growth_phrases
            ), f"Template missing growth phrase: {template}"

    def test_upgrade_with_specific_template(self, generator: MessageGenerator) -> None:
        """Test plan_upgrade method with mocked template selection."""
        event = {
            "customer_name": "Acme Corp",
            "old_plan": "Basic",
            "new_plan": "Pro",
        }

        with patch("webhooks.message_generator.random.choice") as mock_choice:
            mock_choice.return_value = generator.UPGRADE_TEMPLATES[0]
            message = generator.plan_upgrade(event)

        assert "Acme Corp" in message
        assert "Pro" in message
        assert "🎉" in message  # First template uses this emoji


class TestBrandVoice:
    """Tests for consistent brand voice across all message types."""

    @pytest.mark.parametrize(
        "event_type,templates_attr",
        [
            ("payment_success", "PAYMENT_SUCCESS_TEMPLATES"),
            ("payment_failure", "PAYMENT_FAILURE_TEMPLATES"),
            ("trial_ending", "TRIAL_ENDING_TEMPLATES"),
            ("plan_upgrade", "UPGRADE_TEMPLATES"),
        ],
    )
    def test_messages_maintain_brand_voice(
        self,
        generator: MessageGenerator,
        event_type: str,
        templates_attr: str,
    ) -> None:
        """Test that all messages maintain our brand voice regardless of situation.

        Verifies no formal corporate language, includes emojis, uses customer
        name, and stays concise.
        """
        event: dict[str, Any] = {"type": event_type, "customer_name": "Acme"}
        templates = getattr(generator, templates_attr)
        formal_phrases = [
            "Dear customer",
            "We regret to inform",
            "Please be advised",
            "Hereby",
            "Pursuant to",
        ]

        # Test with each template to ensure deterministic behavior
        for template in templates:
            with patch("webhooks.message_generator.random.choice") as mock_choice:
                mock_choice.return_value = template
                message = generator.generate(event)

            assert not any(
                phrase in message for phrase in formal_phrases
            ), f"Template contains formal language: {template}"
            assert any(
                char in generator.ALL_EMOJI for char in message
            ), f"Template missing emoji: {template}"
            assert (
                event["customer_name"] in message
            ), f"Template missing customer: {template}"
            assert len(message.split()) < 50, f"Template too long: {template}"

    def test_generate_with_unknown_event_type(
        self, generator: MessageGenerator
    ) -> None:
        """Test that unknown event types still produce valid messages."""
        event = {"type": "unknown_event", "customer_name": "Acme Corp"}
        message = generator.generate(event)

        assert "Acme Corp" in message
        assert any(char in generator.ALL_EMOJI for char in message)
