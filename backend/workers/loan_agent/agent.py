from workers.base_worker import BaseWorkerAgent


class LoanAgent(BaseWorkerAgent):
    domain_scheme_ids = [
        "kisan_credit_card",
        "retail_micro_loan",
        "pm_mudra_yojana_shishu",
        "home_loan",
    ]
