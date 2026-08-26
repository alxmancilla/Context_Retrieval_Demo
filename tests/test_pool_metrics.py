from core.pool_metrics import PoolMetrics


def test_pool_metrics_track_checkout_gauge_and_failures():
    metrics = PoolMetrics()
    metrics.connection_check_out_started(None)
    metrics.connection_checked_out(None)
    metrics.connection_checked_out(None)
    metrics.connection_checked_in(None)
    metrics.connection_check_out_failed(None)
    assert metrics.snapshot() == {
        "checkout_started": 1,
        "checkout_succeeded": 2,
        "checkout_failed": 1,
        "checked_out": 1,
        "max_checked_out": 2,
    }