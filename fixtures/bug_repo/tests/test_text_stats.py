from cpu_bench_demo import extract_error_codes, summarize_counts


def test_extract_error_codes_keeps_prefix():
    assert extract_error_codes("ok ERR-104 retry ERR-205 done") == ["ERR-104", "ERR-205"]


def test_summarize_counts_uses_float_mean():
    assert summarize_counts([1, 2]) == {"count": 2, "mean": 1.5}
