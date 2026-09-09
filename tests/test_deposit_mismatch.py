from delta_backend.deposit_mismatch import select_mismatch_candidate


def test_select_by_base_minor():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 1, "amount_minor": 100_000000, "created_at": 1010, "tx_hash": "0xa", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 1


def test_select_within_one_usdt_of_exact():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 2, "amount_minor": 100_370000 - 50, "created_at": 1010, "tx_hash": "0xb", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 2


def test_reject_outside_window_and_tolerance():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    far = {"id": 3, "amount_minor": 50_000000, "created_at": 1010, "tx_hash": "0xc", "matched": 0}
    early = {"id": 4, "amount_minor": 100_000000, "created_at": 100, "tx_hash": "0xd", "matched": 0}
    assert select_mismatch_candidate(invoice, [far, early]) is None


def test_prefer_closest_created_at_then_smaller_delta():
    invoice = {"created_at": 1000, "expires_at": 2000, "base_minor": 100_000000, "exact_minor": 100_370000}
    candidates = [
        {"id": 5, "amount_minor": 100_000000, "created_at": 1500, "tx_hash": "0xe", "matched": 0},
        {"id": 6, "amount_minor": 100_000000, "created_at": 1050, "tx_hash": "0xf", "matched": 0},
    ]
    assert select_mismatch_candidate(invoice, candidates)["id"] == 6
