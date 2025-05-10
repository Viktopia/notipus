from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Organization, NotificationSettings


@receiver(post_save, sender=Organization)
def create_notification_settings(sender, instance, created, **kwargs):
    if created:
        NotificationSettings.objects.create(organization=instance)
