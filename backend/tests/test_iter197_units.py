"""Unit tests for the imperial/metric conversion helpers."""
import pytest
from shipment_units import (
    parse_dim_to_cm,
    parse_weight_to_kg,
    format_dim_cm,
    format_weight_kg,
    cm_to_feet_inches,
    kg_to_lb_oz,
)


class TestDimParse:
    def test_bare_number_metric_default(self):
        assert parse_dim_to_cm(33) == 33.0
        assert parse_dim_to_cm("33") == 33.0

    def test_bare_number_imperial_treated_as_inches(self):
        assert parse_dim_to_cm(33, "imperial") == pytest.approx(83.82, rel=1e-3)
        assert parse_dim_to_cm("33", "imperial") == pytest.approx(83.82, rel=1e-3)

    def test_cm_suffix(self):
        assert parse_dim_to_cm("84cm") == 84.0
        assert parse_dim_to_cm("84 cm") == 84.0

    def test_metres(self):
        assert parse_dim_to_cm("0.84m") == pytest.approx(84.0, rel=1e-3)
        assert parse_dim_to_cm("2 m") == pytest.approx(200.0, rel=1e-3)

    def test_millimetres(self):
        assert parse_dim_to_cm("840mm") == pytest.approx(84.0, rel=1e-3)

    def test_inches_suffix(self):
        assert parse_dim_to_cm("33in") == pytest.approx(83.82, rel=1e-3)
        assert parse_dim_to_cm("33\"") == pytest.approx(83.82, rel=1e-3)

    def test_feet_inches_combos(self):
        # Iconic example from the user: 2'9" must equal 33"
        assert parse_dim_to_cm("2'9\"") == pytest.approx(83.82, rel=1e-3)
        assert parse_dim_to_cm("2ft 9in") == pytest.approx(83.82, rel=1e-3)
        assert parse_dim_to_cm("2'") == pytest.approx(60.96, rel=1e-3)
        assert parse_dim_to_cm("9in") == pytest.approx(22.86, rel=1e-3)

    def test_empty_or_garbage_returns_zero(self):
        assert parse_dim_to_cm("") == 0.0
        assert parse_dim_to_cm("xyz") == 0.0
        assert parse_dim_to_cm(None) == 0.0


class TestWeightParse:
    def test_bare_kg_default(self):
        assert parse_weight_to_kg(5) == 5.0

    def test_bare_imperial_treated_as_pounds(self):
        assert parse_weight_to_kg(5, "imperial") == pytest.approx(2.268, rel=1e-3)

    def test_kg_suffix(self):
        assert parse_weight_to_kg("2.3kg") == pytest.approx(2.3, rel=1e-6)

    def test_grams(self):
        assert parse_weight_to_kg("2300g") == pytest.approx(2.3, rel=1e-6)

    def test_lb_combos(self):
        assert parse_weight_to_kg("5lb") == pytest.approx(2.268, rel=1e-3)
        assert parse_weight_to_kg("5 lbs") == pytest.approx(2.268, rel=1e-3)
        assert parse_weight_to_kg("5lb 8oz") == pytest.approx(2.495, rel=1e-3)
        assert parse_weight_to_kg("8oz") == pytest.approx(0.2268, rel=1e-3)


class TestFormatters:
    def test_format_dim_metric(self):
        assert format_dim_cm(83.82) == "83.8 cm"
        assert format_dim_cm(250).startswith("2.50 m")

    def test_format_dim_imperial(self):
        # Round-trip: 83.82 cm → ~2'9"
        assert format_dim_cm(83.82, "imperial") == "2'9\""

    def test_format_weight_metric(self):
        assert format_weight_kg(2.27) == "2.27 kg"
        assert format_weight_kg(0.5).endswith("g")

    def test_format_weight_imperial(self):
        out = format_weight_kg(2.268, "imperial")
        assert out.startswith("5 lb")


class TestRoundTrip:
    def test_dim_round_trip_imperial(self):
        cm = parse_dim_to_cm("3'6\"")
        formatted = format_dim_cm(cm, "imperial")
        assert formatted == "3'6\""

    def test_weight_round_trip_imperial(self):
        kg = parse_weight_to_kg("10 lb 4 oz")
        formatted = format_weight_kg(kg, "imperial")
        assert formatted == "10 lb 4 oz"
