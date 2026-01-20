import random
from typing import Any, Dict, List


class MessageGenerator:
    # Emoji collections
    SUCCESS_EMOJI = ["🎉", "💸", "🎊", "🚀", "💪", "🙌", "💥", "👀", "🏆", "🔐"]
    FAILURE_EMOJI = ["😅", "🤔", "👀", "💭", "👋", "🚧", "📢", "📞", "🔔"]
    TRIAL_EMOJI = ["✨", "🌟", "💫", "🚀", "🎯", "⏳", "🎁", "⏰", "🔍"]
    UPGRADE_EMOJI = ["🎉", "🚀", "⭐️", "🌟", "💪", "💥", "🔓", "📈", "🎯", "🌠"]
    ALL_EMOJI = set(SUCCESS_EMOJI + FAILURE_EMOJI + TRIAL_EMOJI + UPGRADE_EMOJI)

    # Message templates with placeholders
    PAYMENT_SUCCESS_TEMPLATES = [
        "🎉 Woohoo! {customer_name} just dropped {amount} in our piggy bank!",
        (
            "💸 Ka-ching! {customer_name} keeps the lights on with a sweet "
            "{amount} payment!"
        ),
        "🎊 Awesome! {customer_name} just sent {amount} our way!",
        "🚀 Nice one! {customer_name} coming through with {amount}!",
        (
            "💪 Sweet! Look who's crushing it! {customer_name} with a solid "
            "{amount} payment!"
        ),
        # New messages
        "🙌 High five! {customer_name} just came through with {amount}!",
        "💥 Boom! {customer_name} is keeping the dream alive with {amount}!",
        "👀 Look at that! {customer_name} just dropped {amount} - you love to see it!",
        "🏆 Winner winner! {customer_name} just paid {amount}!",
        "🔐 The vault just got heavier! {customer_name} sent {amount}!",
    ]

    # Payment failure templates
    PAYMENT_FAILURE_TEMPLATES = [
        "😅 Oops! {customer_name}'s payment didn't go through and needs attention.",
        "🤔 Uh-oh! Looks like {customer_name}'s payment needs looking at.",
        "👀 Seems like {customer_name} hit a snag and needs attention.",
        "💭 Heads up! {customer_name}'s payment could use some attention.",
        # New messages
        "👋 Friendly nudge! {customer_name}'s payment could use a quick check.",
        "🚧 Hey team! {customer_name}'s payment hit a speed bump.",
        "📢 Attention needed! {customer_name}'s payment didn't quite land.",
        "📞 Time to reach out! {customer_name}'s payment needs some TLC.",
        "🔔 Just a heads up! {customer_name}'s payment is waiting for a retry.",
    ]

    # Trial ending templates
    TRIAL_ENDING_TEMPLATES = [
        (
            "✨ {customer_name} is absolutely crushing it with "
            "{popular_features}! Time to level up!"
        ),
        (
            "🌟 Look who's having a blast! {customer_name}'s really getting "
            "into {popular_features}!"
        ),
        "💫 {customer_name}'s loving {popular_features}! Let's keep this going!",
        (
            "🚀 {customer_name}'s been rocking {popular_features}! "
            "Time to make it official!"
        ),
        (
            "✨ The way {customer_name}'s making the most of "
            "{popular_features} is amazing!"
        ),
        # New messages
        "🎯 {customer_name} is wrapping up their trial adventure - time to chat!",
        "⏳ Trial countdown for {customer_name}! They've been loving the product!",
        "🎁 {customer_name}'s free ride is coming to an end - let's help them commit!",
        "⏰ Tick tock! {customer_name}'s trial is in the home stretch!",
        "🔍 {customer_name} has been exploring like a pro - trial ends soon!",
    ]

    # Upgrade templates
    UPGRADE_TEMPLATES = [
        (
            "🎉 🚀 Awesome upgrade! {customer_name} is growing fast, "
            "leveling up from {old_plan} to {new_plan}! Next level achieved! 💪"
        ),
        (
            "⭐️ 🌟 {customer_name} just supercharged to {new_plan}! "
            "They're scaling up and we're here for it! Power up! 🚀"
        ),
        (
            "🚀 💪 Power up! {customer_name}'s expanding rapidly to {new_plan} "
            "and we're absolutely thrilled! Leveled up! ⭐️"
        ),
        (
            "🎉 ⭐️ Next level! {customer_name}'s moving up to {new_plan}! "
            "Supercharged and growing strong! 🌟"
        ),
        (
            "🚀 🌟 Leveled up! {customer_name}'s growing with {new_plan} "
            "powers! Awesome upgrade! 💪"
        ),
        # New messages
        "💥 Boom! {customer_name} just went bigger and better with {new_plan}!",
        "🔓 Growth mode activated! {customer_name} upgraded to {new_plan}!",
        "📈 {customer_name} is scaling up to {new_plan} - what a journey!",
        "🎯 Big moves! {customer_name} just unlocked {new_plan} features!",
        "🌠 The sky's the limit! {customer_name} just upgraded to {new_plan}!",
    ]

    def _format_features(self, features: List[str]) -> str:
        """Format feature list into readable string"""
        if not features:
            return "everything"
        if len(features) == 1:
            return features[0]
        return f"{', '.join(features[:-1])} and {features[-1]}"

    def _ensure_required_fields(
        self, event: Dict[str, Any], required_fields: List[str]
    ) -> Dict[str, Any]:
        """Ensure all required fields are present, with defaults if needed"""
        event = event.copy()
        for field in required_fields:
            if field not in event:
                if field == "amount":
                    event[field] = "some money"
                elif field == "popular_features":
                    event[field] = ["our features"]
                elif field in ["old_plan", "new_plan"]:
                    event[field] = "their plan"
                else:
                    event[field] = "Unknown"
        return event

    def payment_success(self, event: Dict[str, Any]) -> str:
        """Generate a fun payment success message"""
        event = self._ensure_required_fields(event, ["customer_name", "amount"])
        template = random.choice(self.PAYMENT_SUCCESS_TEMPLATES)
        return template.format(**event)

    def payment_failure(self, event: Dict[str, Any]) -> str:
        """Generate a light but clear payment failure message"""
        event = self._ensure_required_fields(event, ["customer_name", "amount"])
        template = random.choice(self.PAYMENT_FAILURE_TEMPLATES)
        return template.format(**event)

    def trial_ending(self, event: Dict[str, Any]) -> str:
        """Generate an encouraging trial ending message"""
        event = self._ensure_required_fields(
            event, ["customer_name", "popular_features"]
        )
        event["popular_features"] = self._format_features(
            event.get("popular_features", [])
        )
        template = random.choice(self.TRIAL_ENDING_TEMPLATES)
        return template.format(**event)

    def plan_upgrade(self, event: Dict[str, Any]) -> str:
        """Generate an extra enthusiastic upgrade message"""
        event = self._ensure_required_fields(
            event, ["customer_name", "old_plan", "new_plan"]
        )
        template = random.choice(self.UPGRADE_TEMPLATES)
        return template.format(**event)

    def generate(self, event: Dict[str, Any]) -> str:
        """Generate appropriate message based on event type"""
        event_type = event.get("type", "unknown")

        if event_type == "payment_success":
            return self.payment_success(event)
        elif event_type == "payment_failure":
            return self.payment_failure(event)
        elif event_type == "trial_ending":
            return self.trial_ending(event)
        elif event_type == "plan_upgrade":
            return self.plan_upgrade(event)
        else:
            # Default to a generic but still fun message
            event = self._ensure_required_fields(event, ["customer_name"])
            return (
                f"✨ Hey! Something's happening with {event['customer_name']}! "
                "Take a look!"
            )
