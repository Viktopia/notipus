from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import (
    NotificationSettings,
    Organization,
    Workspace,
    WorkspaceNotificationSettings,
)


@receiver(post_save, sender=Organization)
def create_notification_settings(sender, instance, created, **kwargs):
    if created:
        NotificationSettings.objects.create(organization=instance)


@receiver(post_save, sender=Workspace)
def create_workspace_notification_settings(sender, instance, created, **kwargs):
    """Create notification settings when a new workspace is created"""
    if created:
        WorkspaceNotificationSettings.objects.create(workspace=instance)
