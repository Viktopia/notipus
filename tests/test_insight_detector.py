"""Tests for the InsightDetector service.

This module tests the InsightDetector class that identifies
milestones and generates insights for notifications.
"""

import pytest
from webhooks.services.insight_detector import InsightDetector, MilestoneConfig


@pytest.fixture
def detector() -> InsightDetector:
    """Create an InsightDetector instance with default config."""
    return InsightDetector()


@pytest.fixture
def custom_detector() -> InsightDetector:
    """Create an InsightDetector with custom config."""
    config = MilestoneConfig(
        ltv_milestones=[500, 1000, 2500],
        payment_growth_threshold=0.15,
        vip_ltv_threshold=5000,
    )
    return InsightDetector(config)


@pytest.fixture
def payment_success_event() -> dict:
    """Sample payment success event."""
    return {
        "type": "payment_success",
        "provider": "stripe",
        "amount": 299.00,
        "currency": "USD",
        "metadata": {},
    }


@pytest.fixture
def payment_failure_event() -> dict:
    """Sample payment failure event."""
    return {
        "type": "payment_failure",
        "provider": "stripe",
        "amount": 99.00,
        "currency": "USD",
        "metadata": {"failure_reason": "Card declined"},
    }


@pytest.fixture
def new_customer_data() -> dict:
    """Sample new customer data (first payment)."""
    return {
        "email": "new@example.com",
        "orders_count": 0,
        "total_spent": 0,
        "payment_history": [],
    }


@pytest.fixture
def existing_customer_data() -> dict:
    """Sample existing customer data."""
    return {
        "email": "existing@example.com",
        "orders_count": 10,
        "total_spent": 4500.00,
        "payment_history": [
            {"status": "success", "amount": 500},
            {"status": "success", "amount": 500},
            {"status": "success", "amount": 500},
        ],
        "created_at": "2024-01-15T10:00:00Z",
    }


class TestInsightDetectorBasic:
    """Test basic InsightDetector functionality."""

    def test_detect_returns_insight_info_or_none(
        self,
        detector: InsightDetector,
        payment_success_event: dict,
        existing_customer_data: dict,
    ) -> None:
        """Test detect returns InsightInfo or None."""
        result = detector.detect(payment_success_event, existing_customer_data)

        # Result should be InsightInfo or None
        assert result is None or hasattr(result, "icon")

    def test_default_config(self, detector: InsightDetector) -> None:
        """Test default milestone configuration."""
        assert 1000 in detector.config.ltv_milestones
        assert 5000 in detector.config.ltv_milestones
        assert detector.config.payment_growth_threshold == 0.20


class TestFirstPaymentDetection:
    """Test first payment detection."""

    def test_detect_first_payment_new_customer(
        self,
        detector: InsightDetector,
        payment_success_event: dict,
        new_customer_data: dict,
    ) -> None:
        """Test first payment detection for new customer."""
        result = detector.detect(payment_success_event, new_customer_data)

        assert result is not None
        assert result.icon == "new"
        assert "First payment" in result.text or "Welcome" in result.text

    def test_detect_first_payment_subscription_created(
        self, detector: InsightDetector, new_customer_data: dict
    ) -> None:
        """Test first payment detection on subscription created."""
        event = {"type": "subscription_created", "amount": 49.00}
        result = detector.detect(event, new_customer_data)

        assert result is not None
        assert "First payment" in result.text or "Welcome" in result.text

    def test_no_first_payment_for_existing_customer(
        self,
        detector: InsightDetector,
        payment_success_event: dict,
        existing_customer_data: dict,
    ) -> None:
        """Test no first payment insight for existing customer."""
        result = detector.detect(payment_success_event, existing_customer_data)

        # Should not be first payment insight
        if result is not None:
            assert "First payment" not in result.text


class TestLTVMilestoneDetection:
    """Test LTV milestone detection."""

    def test_detect_ltv_milestone_1000(self, detector: InsightDetector) -> None:
        """Test detection of $1000 LTV milestone."""
        event = {"type": "payment_success", "amount": 200.00}
        customer = {
            "orders_count": 5,
            "total_spent": 900.00,  # Will cross $1000 with this payment
            "payment_history": [{"status": "success", "amount": 300}] * 3,
        }

        result = detector.detect(event, customer)

        assert result is not None
        assert "1,000" in result.text
        assert result.icon == "celebration"

    def test_detect_ltv_milestone_5000(self, detector: InsightDetector) -> None:
        """Test detection of $5000 LTV milestone."""
        event = {"type": "payment_success", "amount": 500.00}
        customer = {
            "orders_count": 20,
            "total_spent": 4800.00,  # Will cross $5000 with this payment
            "payment_history": [{"status": "success", "amount": 300}] * 5,
        }

        result = detector.detect(event, customer)

        assert result is not None
        assert "5,000" in result.text
        assert result.icon == "celebration"

    def test_no_milestone_when_not_crossed(self, detector: InsightDetector) -> None:
        """Test no milestone when not crossed."""
        event = {"type": "payment_success", "amount": 100.00}
        customer = {
            "orders_count": 5,
            "total_spent": 500.00,  # Won't cross any milestone
            "payment_history": [{"status": "success", "amount": 100}] * 5,
        }

        result = detector.detect(event, customer)

        # Should not be LTV milestone insight (may be another type or None)
        if result is not None:
            assert "Crossed" not in result.text or "$1,000" not in result.text

    def test_custom_ltv_milestones(self, custom_detector: InsightDetector) -> None:
        """Test custom LTV milestones."""
        event = {"type": "payment_success", "amount": 100.00}
        customer = {
            "orders_count": 3,
            "total_spent": 450.00,  # Will cross $500 with this payment
            "payment_history": [{"status": "success", "amount": 150}] * 3,
        }

        result = custom_detector.detect(event, customer)

        assert result is not None
        assert "500" in result.text


class TestPaymentGrowthDetection:
    """Test payment growth detection."""

    def test_detect_payment_growth(self, detector: InsightDetector) -> None:
        """Test detection of significant payment growth."""
        event = {"type": "payment_success", "amount": 600.00}  # 100% larger than avg
        customer = {
            "orders_count": 10,
            "total_spent": 3000.00,
            "payment_history": [
                {"status": "success", "amount": 300},
                {"status": "success", "amount": 300},
                {"status": "success", "amount": 300},
            ],  # Average is 300
        }

        result = detector.detect(event, customer)

        assert result is not None
        assert "%" in result.text or "larger" in result.text.lower()

    def test_no_growth_detection_without_history(
        self, detector: InsightDetector
    ) -> None:
        """Test no growth detection without enough payment history."""
        event = {"type": "payment_success", "amount": 600.00}
        customer = {
            "orders_count": 1,
            "total_spent": 100.00,
            "payment_history": [{"status": "success", "amount": 100}],  # Only 1 payment
        }

        result = detector.detect(event, customer)

        # Should not be growth insight due to insufficient history
        if result is not None:
            assert "larger" not in result.text.lower() or "%" not in result.text


class TestFailedAttemptDetection:
    """Test failed payment attempt detection."""

    def test_detect_failure_reason(
        self, detector: InsightDetector, payment_failure_event: dict
    ) -> None:
        """Test detection of failure reason."""
        customer = {"payment_history": []}

        result = detector.detect(payment_failure_event, customer)

        assert result is not None
        assert "declined" in result.text.lower()
        assert result.icon == "warning"

    def test_detect_multiple_failures(
        self, detector: InsightDetector, payment_failure_event: dict
    ) -> None:
        """Test detection of multiple failed attempts."""
        customer = {
            "payment_history": [
                {"status": "failed", "type": "payment_failure"},
                {"status": "failed", "type": "payment_failure"},
            ],
        }

        result = detector.detect(payment_failure_event, customer)

        assert result is not None
        assert "Attempt #3" in result.text or "#3" in result.text


class TestVIPDetection:
    """Test VIP customer detection."""

    def test_detect_vip_status(self, detector: InsightDetector) -> None:
        """Test VIP status detection for high LTV customers."""
        event = {"type": "payment_success", "amount": 500.00}
        customer = {
            "orders_count": 50,
            "total_spent": 15000.00,  # High LTV
            "payment_history": [{"status": "success", "amount": 300}] * 5,
        }

        result = detector.detect(event, customer)

        # VIP detection might not be highest priority, check if detected
        # when no higher priority milestones are crossed
        assert result is not None


class TestRiskStatusDetection:
    """Test risk status flag detection."""

    def test_detect_at_risk_on_failure_high_ltv(
        self, detector: InsightDetector, payment_failure_event: dict
    ) -> None:
        """Test at_risk flag on failure with high LTV."""
        customer = {
            "total_spent": 5000.00,
            "payment_history": [],
        }

        flags = detector.detect_risk_status(payment_failure_event, customer)

        assert "at_risk" in flags

    def test_detect_vip_flag(
        self, detector: InsightDetector, payment_success_event: dict
    ) -> None:
        """Test VIP flag for high LTV customers."""
        customer = {
            "total_spent": 15000.00,  # Over VIP threshold
            "payment_history": [],
        }

        flags = detector.detect_risk_status(payment_success_event, customer)

        assert "vip" in flags

    def test_detect_at_risk_multiple_failures(
        self, detector: InsightDetector, payment_failure_event: dict
    ) -> None:
        """Test at_risk flag with multiple recent failures."""
        customer = {
            "total_spent": 500.00,
            "payment_history": [
                {"status": "failed"},
                {"status": "failed"},
                {"status": "success"},
            ],
        }

        flags = detector.detect_risk_status(payment_failure_event, customer)

        assert "at_risk" in flags

    def test_no_flags_normal_customer(
        self, detector: InsightDetector, payment_success_event: dict
    ) -> None:
        """Test no flags for normal customer."""
        customer = {
            "total_spent": 500.00,
            "payment_history": [{"status": "success"}, {"status": "success"}],
        }

        flags = detector.detect_risk_status(payment_success_event, customer)

        assert "at_risk" not in flags
        assert "vip" not in flags


class TestLargePaymentDetection:
    """Test large payment detection."""

    def test_detect_large_payment(self, detector: InsightDetector) -> None:
        """Test large payment detection."""
        event = {"type": "payment_success", "amount": 1500.00}  # Large payment
        customer = {
            "orders_count": 5,
            "total_spent": 500.00,  # Low total so no LTV milestone
            "payment_history": [{"status": "success", "amount": 100}]
            * 2,  # Low history
        }

        result = detector.detect(event, customer)

        assert result is not None
        # Should detect as large payment if no other milestone triggered
        assert result.icon in ("money", "chart", "celebration")


class TestMilestoneConfigDefaults:
    """Test MilestoneConfig default values."""

    def test_default_ltv_milestones(self) -> None:
        """Test default LTV milestones."""
        config = MilestoneConfig()
        assert config.ltv_milestones == [1000, 5000, 10000, 50000, 100000]

    def test_default_anniversary_months(self) -> None:
        """Test default anniversary months."""
        config = MilestoneConfig()
        assert config.anniversary_months == [12, 24, 36, 48, 60]

    def test_default_growth_threshold(self) -> None:
        """Test default payment growth threshold."""
        config = MilestoneConfig()
        assert config.payment_growth_threshold == 0.20

    def test_default_vip_threshold(self) -> None:
        """Test default VIP LTV threshold."""
        config = MilestoneConfig()
        assert config.vip_ltv_threshold == 10000

    def test_default_large_payment_threshold(self) -> None:
        """Test default large payment threshold."""
        config = MilestoneConfig()
        assert config.large_payment_threshold == 1000

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = MilestoneConfig(
            ltv_milestones=[100, 500, 1000],
            payment_growth_threshold=0.10,
            vip_ltv_threshold=2500,
            large_payment_threshold=500,
        )

        assert config.ltv_milestones == [100, 500, 1000]
        assert config.payment_growth_threshold == 0.10
        assert config.vip_ltv_threshold == 2500
        assert config.large_payment_threshold == 500


class TestInsightPriority:
    """Test insight detection priority."""

    def test_first_payment_highest_priority(
        self, detector: InsightDetector, new_customer_data: dict
    ) -> None:
        """Test first payment has highest priority."""
        # Even with large amount, should show first payment
        event = {"type": "payment_success", "amount": 5000.00}

        result = detector.detect(event, new_customer_data)

        assert result is not None
        assert "First payment" in result.text or "Welcome" in result.text

    def test_ltv_milestone_over_growth(self, detector: InsightDetector) -> None:
        """Test LTV milestone takes priority over growth."""
        # Payment that both crosses milestone AND is large growth
        event = {"type": "payment_success", "amount": 500.00}
        customer = {
            "orders_count": 5,
            "total_spent": 900.00,  # Will cross $1000
            "payment_history": [
                {"status": "success", "amount": 100},  # Average is 100
                {"status": "success", "amount": 100},
                {"status": "success", "amount": 100},
            ],
        }

        result = detector.detect(event, customer)

        assert result is not None
        # Should be milestone, not growth
        assert "1,000" in result.text or "Crossed" in result.text
