from django.db import models
from django.contrib.auth.models import User


class Organization(models.Model):
    slack_team_id = models.CharField(max_length=255, unique=True)
    slack_domain = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    slack_user_id = models.CharField(max_length=255, unique=True)
    slack_team_id = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
