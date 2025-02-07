from app.webhooks.models.notification import Notification, Section


# @pytest.mark.django_db
def test_payment_failure_message_structure():
    """Test that payment failure messages have the correct structure"""
    notification = Notification(
        title="Payment Failed",
        sections=[
            Section(
                title="Payment Details",
                fields={
                    "Amount": "$29.99",
                    "Status": "Failed",
                },
            ),
            Section(
                title="Customer Details",
                fields={
                    "Company": "Acme Corp",
                    "Team Size": "50",
                    "Plan": "Enterprise",
                },
            ),
        ],
        color="#dc3545",  # Красный
        emoji="🚨",
    )

    # Если Notification является Django-моделью, возможно, придётся сохранять объект,
    # либо тестировать метод до сохранения, если он не зависит от базы данных.
    assert notification.status == "failed"
    assert notification.color == "#dc3545"

    message = notification.to_slack_message()
    assert message["color"] == "#dc3545"
    assert len(message["blocks"]) == 3  # Заголовок + 2 секции


# @pytest.mark.django_db
def test_trial_end_message_structure():
    """Test that trial end messages have the correct structure"""
    notification = Notification(
        title="Trial Ending Soon",
        sections=[
            Section(
                title="Trial Status",
                fields={
                    "Time Remaining": "7 days",
                    "Plan": "Enterprise",
                },
            ),
            Section(
                title="Customer Details",
                fields={
                    "Company": "Acme Corp",
                    "Team Size": "50",
                    "Plan": "Enterprise",
                },
            ),
        ],
        color="#ffc107",  # Желтый
        emoji="📢",
    )

    assert notification.status == "warning"
    assert notification.color == "#ffc107"

    message = notification.to_slack_message()
    assert message["color"] == "#ffc107"
    assert len(message["blocks"]) == 3  # Заголовок + 2 секции


# @pytest.mark.django_db
def test_message_color_by_type():
    """Test that message color is set based on event type"""
    failure_notification = Notification(
        title="Payment Failed",
        sections=[],
        color="#dc3545",  # Красный
        emoji="🚨",
    )
    assert failure_notification.status == "failed"
    assert failure_notification.color == "#dc3545"

    success_notification = Notification(
        title="Payment Success",
        sections=[],
        color="#28a745",  # Зелёный
        emoji="✅",
    )
    assert success_notification.status == "success"
    assert success_notification.color == "#28a745"

    info_notification = Notification(
        title="Info Message",
        sections=[],
        color="#17a2b8",  # Синий (информационный)
        emoji="ℹ️",
    )
    assert info_notification.status == "info"
    assert info_notification.color == "#17a2b8"


# @pytest.mark.django_db
def test_status_color_sync():
    """Test that status and color stay in sync"""
    notification = Notification(
        title="Test",
        sections=[],
    )

    # Тест изменения статуса
    notification.status = "success"
    assert notification.status == "success"
    assert notification.color == "#28a745"

    notification.status = "failed"
    assert notification.status == "failed"
    assert notification.color == "#dc3545"

    notification.status = "warning"
    assert notification.status == "warning"
    assert notification.color == "#ffc107"

    # Тест, что неверный статус приводит к значению по умолчанию (info)
    notification.status = "invalid"
    assert notification.status == "info"
    assert notification.color == "#17a2b8"


# @pytest.mark.django_db
def test_action_buttons():
    """Test that action buttons are properly formatted"""
    notification = Notification(
        title="Test",
        sections=[],
        action_buttons=[
            {"text": "View Details", "url": "#"},
            {"text": "Contact Support", "url": "#", "style": "primary"},
        ],
    )

    message = notification.to_slack_message()
    assert len(message["blocks"]) == 2  # Заголовок + блок с кнопками
    actions_block = message["blocks"][1]
    assert actions_block["type"] == "actions"
    assert len(actions_block["elements"]) == 2
    assert actions_block["elements"][0]["text"]["text"] == "View Details"
    assert actions_block["elements"][1]["style"] == "primary"
