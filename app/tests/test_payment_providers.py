import json
import pytest
from unittest.mock import MagicMock, patch, Mock
# Импортируем Django HttpRequest, если нужно (но здесь мы используем MagicMock)
# from django.http import HttpRequest

from webhooks.providers import PaymentProvider, ChargifyProvider, ShopifyProvider
from webhooks.providers.base import InvalidDataError
from webhooks.event_processor import EventProcessor

def test_payment_provider_interface():
    """Test that payment providers implement the required interface"""
    providers = [
        ChargifyProvider(webhook_secret="test_secret"),
        ShopifyProvider(webhook_secret="test_secret"),
    ]

    for provider in providers:
        assert isinstance(provider, PaymentProvider)


def test_chargify_payment_failure_parsing():
    """Test that Chargify payment failure webhooks are properly parsed"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Создаем мок запроса (аналог Flask request)
    mock_request = MagicMock()
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.form = MagicMock()
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    mock_request.POST.dict.return_value = {
        "event": "payment_failure",
        "payload[subscription][id]": "sub_12345",
        "payload[subscription][state]": "past_due",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Company",
        "payload[subscription][product][id]": "prod_789",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[subscription][product][handle]": "enterprise",
        "payload[transaction][id]": "tr_123",
        "payload[transaction][amount_in_cents]": "2999",
        "payload[transaction][type]": "payment",
        "payload[transaction][memo]": "Payment failed: Card declined",
        "payload[transaction][failure_message]": "Card was declined",
        "created_at": "2024-03-15T10:00:00Z",
    }

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "payment_failure"
    assert event["customer_id"] == "cust_456"
    assert event["amount"] == 29.99
    assert event["status"] == "failed"
    assert event["metadata"]["failure_reason"] == "Card was declined"
    assert event["metadata"]["subscription_id"] == "sub_12345"
    assert event["customer_data"]["company_name"] == "Test Company"
    assert event["customer_data"]["plan_name"] == "Enterprise Plan"


def test_shopify_order_parsing():
    """Test that Shopify order webhooks are properly parsed"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    # Создаем мок запроса
    mock_request = MagicMock()
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Order-Id": "123456789",
        "X-Shopify-Api-Version": "2024-01",
    }
    shopify_data = {
        "id": 123456789,
        "order_number": 1001,
        "customer": {
            "id": 456,
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "company": "Test Company",
            "orders_count": 5,
            "total_spent": "299.95",
            "note": "Enterprise customer",
            "tags": ["enterprise", "priority"],
            "default_address": {
                "company": "Test Company",
                "country": "United States",
                "country_code": "US",
            },
            "metafields": [
                {
                    "key": "team_size",
                    "value": "25",
                    "namespace": "customer",
                },
                {
                    "key": "plan_type",
                    "value": "enterprise_annual",
                    "namespace": "subscription",
                },
            ],
        },
        "total_price": "29.99",
        "subtotal_price": "24.99",
        "total_tax": "5.00",
        "currency": "USD",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "created_at": "2024-03-15T10:00:00Z",
        "updated_at": "2024-03-15T10:05:00Z",
        "line_items": [
            {
                "id": 789,
                "title": "Enterprise Plan",
                "quantity": 1,
                "price": "29.99",
                "sku": "ENT-PLAN-1",
                "properties": [
                    {"name": "team_size", "value": "25"},
                    {"name": "plan_type", "value": "annual"},
                ],
            }
        ],
    }

    mock_request.get_json.return_value = shopify_data
    # Обязательно задаём request.data как JSON в виде байтов
    mock_request.data = json.dumps(shopify_data).encode("utf-8")


    event = provider.parse_webhook(mock_request)
    assert event["type"] == "payment_success"
    assert event["customer_id"] == "456"
    assert event["amount"] == 29.99
    assert event["status"] == "success"
    assert event["metadata"]["order_number"] == 1001
    assert event["metadata"]["financial_status"] == "paid"
    assert event["metadata"]["fulfillment_status"] == "fulfilled"


def test_chargify_webhook_validation():
    """Test Chargify webhook signature validation"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Создаем мок запроса с заголовками
    mock_request = MagicMock()
    mock_request.headers = {
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "1234567890abcdef",
        "X-Chargify-Webhook-Id": "webhook_123",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Chargify Webhooks",
    }
    # Передаем корректное тело запроса
    body = b"payload[event]=payment_failure&payload[subscription][id]=sub_12345"
    mock_request.get_data.return_value = body  # Байты
    mock_request.body = body  # Для совместимости с методом validate_webhook

    # Патчим hmac.compare_digest
    with patch("hmac.compare_digest", return_value=True):
        assert provider.validate_webhook(mock_request) is True




def test_shopify_webhook_validation():
    """Test Shopify webhook signature validation"""
    provider = ShopifyProvider("test_secret")

    # Создаем мок запроса с валидной сигнатурой
    mock_request = Mock()
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "crxL3PMfBMvgMYyppPUPjAooPtjS7fh0dOiGPTYm3QU=",
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Test": "true",
    }
    mock_request.content_type = "application/json"
    mock_request.body = b'{"test": "data"}'  # Явно задаем атрибут body

    # Тест валидной сигнатуры
    with patch("hmac.new") as mock_hmac:
        mock_hmac.return_value.digest.return_value = b"test_digest"
        mock_b64encode = Mock(return_value=b"crxL3PMfBMvgMYyppPUPjAooPtjS7fh0dOiGPTYm3QU=")
        with patch("base64.b64encode", mock_b64encode):
            assert provider.validate_webhook(mock_request)

    # Тест отсутствия сигнатуры
    mock_request.headers.pop("X-Shopify-Hmac-SHA256")
    assert not provider.validate_webhook(mock_request)

    # Тест отсутствия топика
    mock_request.headers["X-Shopify-Hmac-SHA256"] = "test_signature"
    mock_request.headers.pop("X-Shopify-Topic")
    assert not provider.validate_webhook(mock_request)


    # Тест отсутствия домена магазина
    mock_request.headers["X-Shopify-Topic"] = "orders/paid"
    mock_request.headers.pop("X-Shopify-Shop-Domain")
    assert not provider.validate_webhook(mock_request)

    # Тест неверной сигнатуры
    mock_request.headers.update({
        "X-Shopify-Hmac-SHA256": "invalid_signature",
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
    })
    assert not provider.validate_webhook(mock_request)


@pytest.mark.usefixtures("mock_webhook_validation")
def test_shopify_test_webhook(monkeypatch):
    """Test handling of Shopify test webhooks"""
    provider = ShopifyProvider("test_secret")

    # Создаем мок запроса
    mock_request = Mock()
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Topic": "test",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
    }
    mock_request.content_type = "application/json"
    mock_request.data = b'{"test": true}'
    mock_request.get_json.return_value = {"test": True}

    # Для тестовых вебхуков должно возвращаться None (игнорирование)
    event = provider.parse_webhook(mock_request)
    assert event is None


def test_shopify_invalid_webhook_data():
    """Test handling of invalid Shopify webhook data"""
    provider = ShopifyProvider("test_secret")

    # Создаем мок запроса
    mock_request = Mock()
    mock_request.headers = {
        "X-Shopify-Hmac-SHA256": "test_signature",
        "X-Shopify-Topic": "orders/paid",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
    }
    mock_request.content_type = "application/json"

    # Тест неверного content type
    mock_request.content_type = "application/x-www-form-urlencoded"
    with pytest.raises(InvalidDataError, match="Invalid content type"):
        provider.parse_webhook(mock_request)

    # Тест пустых данных
    mock_request.content_type = "application/json"
    mock_request.data = b"{}"
    mock_request.get_json.return_value = {}
    with pytest.raises(InvalidDataError, match="Missing required fields"):
        provider.parse_webhook(mock_request)

    # Тест отсутствия customer_id
    mock_request.get_json.return_value = {"test": "data"}
    with pytest.raises(InvalidDataError, match="Missing required fields"):
        provider.parse_webhook(mock_request)

    # Тест неверного формата суммы
    mock_request.get_json.return_value = {"id": 123, "total_price": "invalid"}
    with pytest.raises(InvalidDataError, match="Missing required fields"):
        provider.parse_webhook(mock_request)


def test_invalid_webhook_data():
    """Test handling of invalid webhook data for Chargify"""
    chargify = ChargifyProvider(webhook_secret="test_secret")

    # Тест Chargify с некорректными данными
    mock_chargify_request = MagicMock()
    mock_chargify_request.content_type = "application/x-www-form-urlencoded"
    mock_chargify_request.form = MagicMock()
    mock_chargify_request.POST.dict.return_value = {}
    mock_chargify_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }

    with pytest.raises(InvalidDataError, match="Missing required fields"):
        chargify.parse_webhook(mock_chargify_request)


def test_chargify_subscription_state_change():
    """Test parsing of Chargify subscription state change webhook"""
    provider = ChargifyProvider(webhook_secret="test_secret")
    provider._webhook_cache.clear()  # Очищаем кэш перед тестом

    mock_request = MagicMock()
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.form = MagicMock()
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    mock_request.POST.dict.return_value = {
        "event": "subscription_state_change",
        "payload[subscription][id]": "sub_12345",
        "payload[subscription][state]": "canceled",
        "payload[subscription][cancel_at_end_of_period]": "true",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][organization]": "Test Company",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[subscription][product][handle]": "enterprise",
        "payload[subscription][total_revenue_in_cents]": "299900",
        "created_at": "2024-03-15T10:00:00Z",
    }

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "subscription_state_change"
    assert event["customer_id"] == "cust_456"
    assert event["status"] == "canceled"
    assert event["metadata"]["subscription_id"] == "sub_12345"
    assert event["metadata"]["cancel_at_period_end"]
    assert event["customer_data"]["company_name"] == "Test Company"
    assert event["customer_data"]["plan_name"] == "Enterprise Plan"


def test_shopify_customer_data_update():
    """Test parsing of Shopify customers/update webhook"""
    provider = ShopifyProvider(webhook_secret="test_secret")

    mock_request = Mock()
    mock_request.content_type = "application/json"
    mock_request.headers = {
        "X-Shopify-Topic": "customers/update",
        "X-Shopify-Shop-Domain": "test.myshopify.com",
        "X-Shopify-Hmac-SHA256": "test_signature",
    }
    mock_data = {
        "id": 456,
        "email": "test@example.com",
        "accepts_marketing": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-03-15T10:00:00Z",
        "first_name": "Test",
        "last_name": "User",
        "company": "Updated Company Name",
        "orders_count": 10,
        "total_spent": "599.90",
        "note": "Enterprise customer, upgraded plan",
        "tags": ["enterprise", "priority", "annual"],
        "addresses": [
            {
                "id": 1,
                "company": "Updated Company Name",
                "country": "United States",
                "country_code": "US",
            }
        ],
        "metafields": [
            {
                "key": "team_size",
                "value": "50",
                "namespace": "customer",
            },
            {
                "key": "plan_type",
                "value": "enterprise_annual",
                "namespace": "subscription",
            },
        ],
    }
    mock_request.get_json.return_value = mock_data
    mock_request.data = json.dumps(mock_data).encode("utf-8")
    

    event = provider.parse_webhook(mock_request)
    assert event is not None
    assert event["type"] == "customers/update"
    assert event["customer_id"] == "456"
    assert event["customer_data"]["company"] == "Updated Company Name"


def test_chargify_webhook_deduplication():
    """Test Chargify webhook deduplication logic"""
    provider = ChargifyProvider("")
    provider._DEDUP_WINDOW_SECONDS = 60  # Устанавливаем окно дедупликации на 60 секунд для теста

    # Создаем мок запроса с событием payment_success
    mock_request = MagicMock()
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.form = MagicMock()
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "test_webhook_1",
    }
    form_data = {
        "event": "payment_success",
        "id": "12345",
        "payload[subscription][id]": "sub_789",
        "payload[subscription][customer][id]": "cust_123",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Co",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[transaction][amount_in_cents]": "10000",
        "created_at": "2024-03-15T10:00:00Z",
    }
    # mock_form = MagicMock()
    # mock_form.POST.dict.return_value = form_data
    # mock_request.form = mock_form
    mock_request.POST.dict.return_value = form_data
    # Первое событие должно обработаться
    event1 = provider.parse_webhook(mock_request)
    assert event1 is not None
    assert event1["type"] == "payment_success"
    assert event1["customer_id"] == "cust_123"

    # Для того же customer в рамках дедупликационного окна событие должно считаться дубликатом
    mock_request.headers["X-Chargify-Webhook-Id"] = "different_webhook_id"
    form_data["event"] = "renewal_success"  # меняем тип события
    mock_request.POST.dict.return_value = form_data
    with pytest.raises(InvalidDataError, match="Duplicate webhook for customer"):
        provider.parse_webhook(mock_request)

    # Для другого customer событие должно обработаться
    mock_request.headers["X-Chargify-Webhook-Id"] = "test_webhook_3"
    form_data["event"] = "payment_success"
    form_data["payload[subscription][customer][id]"] = "cust_456"
    form_data["payload[subscription][customer][email]"] = "other@example.com"
    mock_request.POST.dict.return_value = form_data
    event3 = provider.parse_webhook(mock_request)
    assert event3 is not None
    assert event3["type"] == "payment_success"
    assert event3["customer_id"] == "cust_456"

    # Тест очистки кэша – события вне дедупликационного окна
    provider._DEDUP_WINDOW_SECONDS = 0  # Устанавливаем окно в 0 для принудительной очистки
    mock_request.headers["X-Chargify-Webhook-Id"] = "test_webhook_4"
    form_data["payload[subscription][customer][id]"] = "cust_123"  # возвращаем первого клиента
    form_data["payload[subscription][customer][email]"] = "test@example.com"
    mock_request.POST.dict.return_value = form_data
    event4 = provider.parse_webhook(mock_request)
    assert event4 is not None
    assert event4["type"] == "payment_success"
    assert event4["customer_id"] == "cust_123"


def test_event_processor_notification_formatting():
    """Test that EventProcessor correctly formats notifications for various event types"""
    processor = EventProcessor()

    # Тест успешного платежного события
    event_data = {
        "type": "payment_success",
        "customer_id": "cust_123",
        "amount": 29.99,
        "currency": "USD",
        "status": "success",
        "metadata": {
            "subscription_id": "sub_123",
            "plan": "enterprise",
        },
    }
    customer_data = {
        "company": "Acme Corp",
        "team_size": "50",
        "plan": "Enterprise",
    }

    notification = processor.format_notification(event_data, customer_data)
    assert notification.title == "Payment Received: $29.99"
    assert notification.status == "success"
    assert len(notification.sections) == 3  # Event Details, Customer Details, and Metadata
    assert notification.sections[0].title == "Event Details"
    assert notification.sections[1].title == "Customer Details"
    assert notification.sections[2].title == "Additional Details"

    # Тест для события неуспешного платежа
    event_data["type"] = "payment_failure"
    event_data["status"] = "failed"
    event_data["metadata"]["failure_reason"] = "card_declined"

    notification = processor.format_notification(event_data, customer_data)
    assert notification.title == "Payment Failed"
    assert notification.color == "#dc3545"  # Красный для ошибки
    assert len(notification.sections) == 3  # Event Details, Customer Details, and Metadata
    # Проверяем, что в метаданных содержится причина ошибки.
    # Если структура fields отличается, возможно, понадобится адаптировать проверку.
    assert "card_declined" in notification.sections[2].fields[2]


def test_chargify_memo_parsing():
    """Test that Chargify memo field is correctly parsed for Shopify order references"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Тестируем различные форматы memo
    test_cases = [
        (
            "Wire payment received for $233.76 24th December '24\n$228.90 allocated to Shopify Order 2067",
            "2067",
        ),
        ("Payment for Shopify Order 1234", "1234"),
        ("$500 allocated to order 5678", "5678"),
        ("Regular payment - no order reference", None),
        (
            "Multiple orders: allocated to 1111 and Shopify Order 2222",
            "2222",  # Приоритет отдается явному упоминанию Shopify Order
        ),
        (
            "Order 3333 and Shopify Order 4444",
            "4444",  # Приоритет отдается явному упоминанию Shopify Order
        ),
        (
            "Just Order 5555",
            "5555",  # Соответствие по шаблону общего order reference
        ),
        (
            "",  # Пустой memo
            None,
        ),
    ]

    for memo, expected_ref in test_cases:
        ref = provider._parse_shopify_order_ref(memo)
        assert ref == expected_ref, f"Failed to parse memo: {memo}"


def test_chargify_payment_success_with_shopify_ref():
    """Test that payment_success webhook includes Shopify order reference when present"""
    provider = ChargifyProvider(webhook_secret="test_secret")

    # Создаем мок запроса
    mock_request = MagicMock()
    mock_request.content_type = "application/x-www-form-urlencoded"
    mock_request.form = MagicMock()
    mock_request.headers = {
        "X-Chargify-Webhook-Id": "webhook_123",
        "X-Chargify-Webhook-Signature-Hmac-Sha-256": "test_signature",
    }
    mock_request.POST.dict.return_value = {
        "event": "payment_success",
        "payload[subscription][id]": "sub_12345",
        "payload[subscription][customer][id]": "cust_456",
        "payload[subscription][customer][email]": "test@example.com",
        "payload[subscription][customer][first_name]": "Test",
        "payload[subscription][customer][last_name]": "User",
        "payload[subscription][customer][organization]": "Test Company",
        "payload[subscription][product][name]": "Enterprise Plan",
        "payload[transaction][id]": "tr_123",
        "payload[transaction][amount_in_cents]": "10000",
        "payload[transaction][memo]": "Wire payment received for $100.00\nAllocated to Shopify Order 1234",
        "created_at": "2024-03-15T10:00:00Z",
    }

    event = provider.parse_webhook(mock_request)
    assert event["type"] == "payment_success"
    assert event["metadata"]["shopify_order_ref"] == "1234"
    assert "memo" in event["metadata"]  # Полное memo должно быть сохранено


def test_shopify_order_ref_matching():
    """Test that Shopify and Chargify events are correctly linked by order reference"""
    processor = EventProcessor()

    # Создаем событие Shopify заказа
    shopify_event = {
        "type": "payment_success",
        "provider": "shopify",
        "metadata": {
            "order_number": "1234",
            "order_ref": "1234",
        },
    }

    # Создаем событие платежа из Chargify
    chargify_event = {
        "type": "payment_success",
        "provider": "chargify",
        "metadata": {
            "shopify_order_ref": "1234",
            "memo": "Payment for Shopify Order 1234",
        },
    }

    # Тест связывания: Shopify -> Chargify
    processed_shopify = processor._link_related_events(shopify_event)
    assert processed_shopify["metadata"]["order_ref"] == "1234"

    # Тест связывания: Chargify -> Shopify
    processed_chargify = processor._link_related_events(chargify_event)
    assert processed_chargify["metadata"]["related_order_ref"] == "1234"
