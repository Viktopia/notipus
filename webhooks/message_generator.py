import random
from typing import Dict, Any, List


class MessageGenerator:
    # Emoji collections
    SUCCESS_EMOJI = ["🎉", "💸", "🎊", "🚀", "💪"]
    FAILURE_EMOJI = ["😅", "🤔", "👀", "💭"]
    TRIAL_EMOJI = ["✨", "🌟", "💫", "🚀"]
    UPGRADE_EMOJI = ["🎉", "🚀", "⭐️", "🌟", "💪"]
    ALL_EMOJI = set(SUCCESS_EMOJI + FAILURE_EMOJI + TRIAL_EMOJI + UPGRADE_EMOJI)

    # Message templates with placeholders
    PAYMENT_SUCCESS_TEMPLATES = [
        "🎉 Woohoo! {customer_name} just dropped {amount} in our piggy bank!",
        "💸 Ka-ching! {customer_name} keeps the lights on with a sweet {amount} payment!",
        "🎊 Awesome! {customer_name} just sent {amount} our way!",
        "🚀 Nice one! {customer_name} coming through with {amount}!",
        "💪 Sweet! Look who's crushing it! {customer_name} with a solid {amount} payment!",
    ]

    PAYMENT_FAILURE_TEMPLATES = [
        "😅 Oops! {customer_name}'s payment of {amount} needs attention!",
        "🤔 Uh-oh! {customer_name}'s {amount} payment needs looking at!",
        "👀 Looks like {customer_name}'s payment ({amount}) needs attention!",
        "💭 Seems like {customer_name}'s {amount} payment needs looking at!",
        "😅 Uh-oh! {customer_name}'s payment for {amount} needs attention!",
    ]

    TRIAL_ENDING_TEMPLATES = [
        "✨ {customer_name} is absolutely crushing it with {popular_features}! Time to level up!",
        "🌟 Look who's having a blast! {customer_name}'s really getting into {popular_features}!",
        "💫 {customer_name}'s loving {popular_features}! Let's keep this going!",
        "🚀 {customer_name}'s been rocking {popular_features}! Time to make it official!",
        "✨ The way {customer_name}'s making the most of {popular_features} is amazing!",
    ]

    UPGRADE_TEMPLATES = [
        "🎉 🚀 Awesome upgrade! {customer_name} is growing fast, leveling up from {old_plan} to {new_plan}! Next level achieved! 💪",
        "⭐️ 🌟 {customer_name} just supercharged to {new_plan}! They're scaling up and we're here for it! Power up! 🚀",
        "🚀 💪 Power up! {customer_name}'s expanding rapidly to {new_plan} and we're absolutely thrilled! Leveled up! ⭐️",
        "🎉 ⭐️ Next level! {customer_name}'s moving up to {new_plan}! Supercharged and growing strong! 🌟",
        "🚀 🌟 Leveled up! {customer_name}'s growing with {new_plan} powers! Awesome upgrade! 💪",
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
            return f"✨ Hey! Something's happening with {event['customer_name']}! Take a look!"
