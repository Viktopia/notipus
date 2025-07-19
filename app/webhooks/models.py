
from django.db import models
from django.utils import timezone


class PaymentRecord(models.Model):
    """Store payment records from various providers"""

    PROVIDER_CHOICES = [
        ('chargify', 'Chargify'),
        ('stripe', 'Stripe'),
        ('shopify', 'Shopify'),
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
    ]

    # Provider and external IDs
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    external_id = models.CharField(max_length=255)  # Provider's payment ID
    customer_id = models.CharField(max_length=255)  # Provider's customer ID

    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Cross-reference fields
    shopify_order_ref = models.CharField(max_length=255, blank=True, default='')
    chargify_transaction_id = models.CharField(max_length=255, blank=True, default='')
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default='')

    # Metadata and timestamps
    metadata = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['provider', 'external_id']
        indexes = [
            models.Index(fields=['customer_id']),
            models.Index(fields=['shopify_order_ref']),
            models.Index(fields=['chargify_transaction_id']),
            models.Index(fields=['stripe_payment_intent_id']),
            models.Index(fields=['processed_at']),
        ]

    def __str__(self) -> str:
        return f"{self.provider} payment {self.external_id} - {self.status}"


class OrderRecord(models.Model):
    """Store order records from e-commerce platforms"""

    PLATFORM_CHOICES = [
        ('shopify', 'Shopify'),
    ]

    STATUS_CHOICES = [
        ('paid', 'Paid'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    # Platform and external IDs
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    external_id = models.CharField(max_length=255)  # Platform's order ID
    order_number = models.CharField(max_length=255, blank=True, default='')
    customer_id = models.CharField(max_length=255)  # Platform's customer ID

    # Order details
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Cross-reference to payments
    related_payment = models.ForeignKey(
        PaymentRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='related_orders'
    )

    # Metadata and timestamps
    metadata = models.JSONField(default=dict, blank=True)
    order_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['platform', 'external_id']
        indexes = [
            models.Index(fields=['customer_id']),
            models.Index(fields=['order_number']),
            models.Index(fields=['order_date']),
        ]

    def __str__(self) -> str:
        order_ref = self.order_number or self.external_id
        return f"{self.platform} order {order_ref} - {self.status}"


class CrossReferenceLog(models.Model):
    """Log cross-reference attempts for debugging and monitoring"""

    LOOKUP_TYPE_CHOICES = [
        ('shopify_to_chargify', 'Shopify Order to Chargify Payment'),
        ('chargify_to_shopify', 'Chargify Payment to Shopify Order'),
    ]

    lookup_type = models.CharField(max_length=30, choices=LOOKUP_TYPE_CHOICES)
    source_ref = models.CharField(max_length=255)
    target_ref = models.CharField(max_length=255, blank=True, default='')
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['lookup_type', 'source_ref']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"{self.lookup_type}: {self.source_ref} -> {self.target_ref} ({status})"
