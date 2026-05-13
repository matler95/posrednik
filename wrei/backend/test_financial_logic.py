import pytest
from backend.model import (
    price_gap_ratio,
    transaction_gap_ratio,
    market_position,
    value_growth_bonus,
    calculate_anomaly_score,
    calculate_preliminary_score,
    opportunity_score,
    condition_multiplier
)

def test_price_gap_ratio():
    assert price_gap_ratio(80_000, 100_000) == 0.2000
    assert price_gap_ratio(100_000, 80_000) == 0.0
    assert price_gap_ratio(None, 100_000) == 0.0
    assert price_gap_ratio(100_000, None) == 0.0
    assert price_gap_ratio(100_000, 0) == 0.0

def test_transaction_gap_ratio():
    listing = {"price": 300_000, "area": 50} # 6000 psm
    assert transaction_gap_ratio(listing, 10000) == 0.4000
    assert transaction_gap_ratio(listing, 5000) == -0.2000
    assert transaction_gap_ratio(listing, None) == 0.0
    
    # Missing price/area
    assert transaction_gap_ratio({"price": 300_000}, 10000) == 0.0
    
    # Cap at -0.5
    assert transaction_gap_ratio(listing, 2000) == -0.5000 # raw gap -2.0 -> capped to -0.5
    
def test_value_growth_bonus():
    assert value_growth_bonus(0.12) == 0.10
    assert value_growth_bonus(0.10) == 0.10
    assert value_growth_bonus(0.075) == 0.05
    assert value_growth_bonus(0.0) == 0.0
    assert value_growth_bonus(-0.02) == -0.01

def test_calculate_anomaly_score():
    # Regular listing
    listing = {"price": 500_000, "area": 50}
    assert calculate_anomaly_score(listing, 12000) == 0.0
    
    # Garage/Cellar (< 10m2)
    listing_garage = {"price": 60_000, "area": 8}
    assert calculate_anomaly_score(listing_garage, 10000) == 1.0
    
    # Price too low
    listing_low = {"price": 40_000, "area": 50}
    assert calculate_anomaly_score(listing_low, 10000) == 1.0
    
    # Price > 100M
    listing_high = {"price": 105_000_000, "area": 100}
    assert calculate_anomaly_score(listing_high, 10000) == 1.0

    # Drastically below RCN (<40%)
    listing_cheap = {"price": 300_000, "area": 100} # 3000 psm
    assert calculate_anomaly_score(listing_cheap, 10000) >= 0.8
    
def test_condition_multiplier():
    assert condition_multiplier({"condition": "nowe"}) == 1.0
    assert condition_multiplier({"condition": "bardzo dobry"}) == 0.95
    assert condition_multiplier({"condition": "do remontu"}) == 0.70
    assert condition_multiplier({}) == 0.92

def test_opportunity_score_sanity():
    # If it's a huge anomaly, score should be zeroed
    listing_anomaly = {"price": 1000, "area": 50, "condition": "dobry"}
    score = calculate_preliminary_score(listing_anomaly, {"Warszawa": 10000}, 500000, 10000, 0.05)
    assert score == 0.0 # because anomaly penalty is 1.0
