"""Phase 2 regression suite: hand-crafted profiles x schemes with known
expected outcomes. Reused by every later phase (offline mode, narration
checks, etc.) -- see Section 9 of the architecture doc."""

import pytest

from eligibility_engine.engine import UnknownSchemeError, check_eligibility


def test_sukanya_samriddhi_eligible():
    result = check_eligibility("sukanya_samriddhi", {"has_girl_child_under_10": True, "age": 35})
    assert result.eligible is True
    assert set(result.satisfied) == {"girl_child_under_10", "guardian_age_requirement"}
    assert result.missing == []
    assert result.completion_fraction == 1.0
    assert result.rule_source == "scheme_rules_v1"
    assert result.rule_updated_at == "2026-09-01"


def test_sukanya_samriddhi_definitively_not_eligible():
    result = check_eligibility("sukanya_samriddhi", {"has_girl_child_under_10": False, "age": 35})
    assert result.eligible is False
    assert result.missing == ["girl_child_under_10"]
    assert result.completion_fraction == 0.5


def test_sukanya_samriddhi_missing_info_is_not_eligible():
    result = check_eligibility("sukanya_samriddhi", {"age": 35})
    assert result.eligible is False
    assert result.missing == ["girl_child_under_10"]
    assert result.completion_fraction == 0.5


def test_pm_jan_dhan_eligible():
    result = check_eligibility("pm_jan_dhan_yojana", {"age": 25, "existing_products": []})
    assert result.eligible is True
    assert result.completion_fraction == 1.0


def test_pm_jan_dhan_already_has_account():
    result = check_eligibility(
        "pm_jan_dhan_yojana", {"age": 25, "existing_products": ["jan_dhan_account"]}
    )
    assert result.eligible is False
    assert result.missing == ["no_existing_basic_account"]


def test_pmay_eligible():
    result = check_eligibility(
        "pmay_rural_housing_subsidy",
        {"monthly_income": 20000, "owns_pucca_house": False, "is_first_time_home_buyer": True},
    )
    assert result.eligible is True
    assert result.completion_fraction == 1.0


def test_pmay_partial_missing_one_field():
    result = check_eligibility(
        "pmay_rural_housing_subsidy",
        {"monthly_income": 20000, "owns_pucca_house": False},
    )
    assert result.eligible is False
    assert result.missing == ["first_time_buyer"]
    assert result.completion_fraction == pytest.approx(2 / 3)


def test_kisan_credit_card_eligible():
    result = check_eligibility(
        "kisan_credit_card",
        {"employment_type": "farmer", "land_holding_acres": 2.5, "age": 45},
    )
    assert result.eligible is True
    assert result.completion_fraction == 1.0


def test_kisan_credit_card_age_out_of_range():
    result = check_eligibility(
        "kisan_credit_card",
        {"employment_type": "farmer", "land_holding_acres": 2.5, "age": 80},
    )
    assert result.eligible is False
    assert result.missing == ["max_age"]
    assert result.completion_fraction == 0.75


def test_retail_micro_loan_eligible_via_salaried_branch_of_or_group():
    result = check_eligibility(
        "retail_micro_loan",
        {"employment_type": "salaried", "monthly_income": 20000, "age": 30, "dependents": 2},
    )
    assert result.eligible is True
    # The OR group is satisfied via the salaried branch -- it must show up
    # as ONE satisfied requirement, not as a contradictory satisfied+missing
    # pair from its two nested branches.
    assert "employment_type_requirement" in result.satisfied
    assert result.missing == []
    assert result.completion_fraction == 1.0


def test_retail_micro_loan_not_eligible_wrong_employment_type():
    result = check_eligibility(
        "retail_micro_loan",
        {"employment_type": "unemployed", "monthly_income": 20000, "age": 30, "dependents": 2},
    )
    assert result.eligible is False
    assert result.missing == ["employment_type_requirement"]


def test_senior_citizen_savings_scheme_single_condition_rule():
    assert check_eligibility("senior_citizen_savings_scheme", {"age": 65}).eligible is True
    assert check_eligibility("senior_citizen_savings_scheme", {"age": 40}).eligible is False


def test_unknown_scheme_raises():
    with pytest.raises(UnknownSchemeError):
        check_eligibility("not_a_real_scheme", {"age": 40})


def test_pm_mudra_yojana_shishu_eligible():
    result = check_eligibility(
        "pm_mudra_yojana_shishu",
        {"employment_type": "self_employed", "age": 30, "has_business_plan": True},
    )
    assert result.eligible is True
    assert result.completion_fraction == 1.0


def test_pm_mudra_yojana_shishu_missing_business_plan():
    result = check_eligibility(
        "pm_mudra_yojana_shishu", {"employment_type": "self_employed", "age": 30}
    )
    assert result.eligible is False
    assert result.missing == ["has_business_plan"]
    assert result.completion_fraction == pytest.approx(3 / 4)


def test_home_loan_eligible_via_or_group_and_property_papers():
    result = check_eligibility(
        "home_loan",
        {
            "employment_type": "self_employed",
            "monthly_income": 35000,
            "age": 40,
            "has_property_papers": True,
        },
    )
    assert result.eligible is True
    assert "employment_type_requirement" in result.satisfied
    assert result.missing == []


def test_home_loan_not_eligible_income_too_low():
    result = check_eligibility(
        "home_loan",
        {
            "employment_type": "salaried",
            "monthly_income": 20000,
            "age": 40,
            "has_property_papers": True,
        },
    )
    assert result.eligible is False
    assert result.missing == ["minimum_income"]


def test_atal_pension_yojana_eligible():
    result = check_eligibility(
        "atal_pension_yojana",
        {"age": 28, "employment_type": "self_employed", "existing_products": []},
    )
    assert result.eligible is True
    assert result.completion_fraction == 1.0


def test_atal_pension_yojana_not_eligible_government_employee():
    result = check_eligibility(
        "atal_pension_yojana",
        {"age": 28, "employment_type": "government_employee", "existing_products": []},
    )
    assert result.eligible is False
    assert result.missing == ["not_government_employee"]


def test_atal_pension_yojana_not_eligible_already_enrolled():
    result = check_eligibility(
        "atal_pension_yojana",
        {
            "age": 28,
            "employment_type": "self_employed",
            "existing_products": ["atal_pension_yojana"],
        },
    )
    assert result.eligible is False
    assert result.missing == ["no_existing_apy_account"]
