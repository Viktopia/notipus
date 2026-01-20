"""Tests for message generator style and tone.

This module tests that generated messages maintain the brand voice
with appropriate emojis, celebratory phrases, and conversational tone.
"""

from webhooks.message_generator import MessageGenerator


def test_payment_success_messages_are_celebratory() -> None:
    """Test that payment success messages have a fun, celebratory tone.

    Verifies emojis and celebratory phrases are included.
    """
    generator = MessageGenerator()

    event = {"customer_name": "Acme Corp", "amount": "$500", "plan": "Pro"}

    message = generator.payment_success(event)
    assert any(emoji in message for emoji in ["🎉", "💸", "🎊", "🚀", "💪"])
    celebratory_phrases = ["Woohoo", "Awesome", "Yay", "Sweet", "Nice one", "Ka-ching"]
    assert any(phrase in message for phrase in celebratory_phrases)
    assert event["customer_name"] in message
    assert event["amount"] in message


def test_payment_failure_messages_are_light_but_clear() -> None:
    """Test that payment failure messages maintain humor while being clear.

    Verifies appropriate emojis and phrases for failure notifications.
    """
    generator = MessageGenerator()

    event = {"customer_name": "Acme Corp", "amount": "$500", "reason": "card_expired"}
    message = generator.payment_failure(event)
    assert any(emoji in message for emoji in ["😅", "🤔", "👀", "💭"])
    light_phrases = ["Oops", "Uh-oh", "Looks like", "Seems like", "Hit a snag"]
    assert any(phrase in message for phrase in light_phrases)
    lower_message = message.lower()
    assert "needs attention" in lower_message or "needs looking at" in lower_message


def test_trial_ending_messages_are_encouraging() -> None:
    """Test that trial ending messages are encouraging and positive.

    Verifies messages highlight product usage and encourage conversion.
    """
    generator = MessageGenerator()

    event = {
        "customer_name": "Acme Corp",
        "trial_usage": "high",
        "popular_features": ["API", "Dashboard"],
    }

    message = generator.trial_ending(event)
    assert any(emoji in message for emoji in ["✨", "🌟", "💫", "🚀"])
    encouraging_phrases = [
        "loving",
        "crushing it",
        "rocking",
        "making the most of",
        "really getting into",
    ]
    assert any(phrase in message.lower() for phrase in encouraging_phrases)
    assert "API" in message or "Dashboard" in message


def test_upgrade_messages_are_extra_celebratory() -> None:
    """Test that upgrade messages are extra enthusiastic.

    Verifies multiple emojis and enthusiastic growth-focused language.
    """
    generator = MessageGenerator()

    event = {
        "customer_name": "Acme Corp",
        "old_plan": "Basic",
        "new_plan": "Pro",
        "team_size": 10,
    }

    message = generator.plan_upgrade(event)
    emoji_count = sum(message.count(emoji) for emoji in ["🎉", "🚀", "⭐️", "🌟", "💪"])
    assert emoji_count >= 2
    enthusiastic_phrases = [
        "Awesome upgrade",
        "Leveled up",
        "Power up",
        "Supercharged",
        "Next level",
    ]
    assert any(phrase in message for phrase in enthusiastic_phrases)
    growth_phrases = ["growing", "scaling", "expanding", "moving up"]
    assert any(phrase in message.lower() for phrase in growth_phrases)


def test_messages_maintain_brand_voice() -> None:
    """Test that all messages maintain our brand voice regardless of situation.

    Verifies no formal corporate language, includes emojis, uses customer
    name, and stays concise.
    """
    generator = MessageGenerator()
    events = [
        {"type": "payment_success", "customer_name": "Acme"},
        {"type": "payment_failure", "customer_name": "Acme"},
        {"type": "trial_ending", "customer_name": "Acme"},
        {"type": "plan_upgrade", "customer_name": "Acme"},
    ]

    for event in events:
        message = generator.generate(event)
        formal_phrases = [
            "Dear customer",
            "We regret to inform",
            "Please be advised",
            "Hereby",
            "Pursuant to",
        ]
        assert not any(phrase in message for phrase in formal_phrases)
        assert any(char in generator.ALL_EMOJI for char in message)
        assert event["customer_name"] in message
        assert len(message.split()) < 50
