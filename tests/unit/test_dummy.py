def test_intentional_failure():
    # Intentionally failing test to trigger CIDRA
    assert 1 == 2, "This test intentionally fails to test CIDRA PR creation"
