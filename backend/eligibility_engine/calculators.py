"""Deterministic financial calculators (EMI / benefit estimates). These never
produce an eligibility verdict -- they are pure arithmetic helpers a worker
agent can cite when narrating benefits of a loan/scheme."""


def calculate_emi(principal: float, annual_rate_percent: float, tenure_months: int) -> dict:
    if tenure_months <= 0:
        raise ValueError("tenure_months must be positive")

    monthly_rate = annual_rate_percent / 12 / 100
    if monthly_rate == 0:
        emi = principal / tenure_months
    else:
        factor = (1 + monthly_rate) ** tenure_months
        emi = principal * monthly_rate * factor / (factor - 1)

    total_payment = emi * tenure_months
    total_interest = total_payment - principal

    return {
        "emi": round(emi, 2),
        "total_payment": round(total_payment, 2),
        "total_interest": round(total_interest, 2),
    }


def calculate_maturity_amount(principal: float, annual_rate_percent: float, tenure_years: int) -> dict:
    if tenure_years <= 0:
        raise ValueError("tenure_years must be positive")

    rate = annual_rate_percent / 100
    maturity_amount = principal * (1 + rate) ** tenure_years
    total_interest = maturity_amount - principal

    return {
        "maturity_amount": round(maturity_amount, 2),
        "total_interest": round(total_interest, 2),
    }
