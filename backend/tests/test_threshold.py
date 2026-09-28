from eligibility_engine.threshold import meets_partial_eligibility_threshold


def test_scheme_specific_threshold():
    assert meets_partial_eligibility_threshold("pm_jan_dhan_yojana", 0.5) is True
    assert meets_partial_eligibility_threshold("pm_jan_dhan_yojana", 0.49) is False


def test_default_threshold_for_unconfigured_scheme():
    assert meets_partial_eligibility_threshold("some_new_scheme", 0.6) is True
    assert meets_partial_eligibility_threshold("some_new_scheme", 0.59) is False
