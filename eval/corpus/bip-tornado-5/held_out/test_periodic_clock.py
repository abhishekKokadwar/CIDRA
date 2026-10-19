"""Held-out tests for bip-tornado-5 (never shown to the model).

The visible test checks a 10 s PeriodicCallback whose clock moves back by 1 to
100 s. These check other periods and a backwards jump right after an overrun:
in every case the next call must be scheduled later than the last one.
"""
import unittest

from tornado.ioloop import PeriodicCallback


def simulate_calls(pc, durations):
    """The times of successive calls, each call lasting `durations[i]` seconds
    (negative: the clock moved back during it). Same model as tornado's own test."""
    calls = []
    now = 1000
    pc._next_timeout = now
    for d in durations:
        pc._update_next(now)
        calls.append(pc._next_timeout)
        now = pc._next_timeout + d
    return calls


class HeldOutPeriodicClockTest(unittest.TestCase):
    def test_small_backwards_steps_keep_a_5s_schedule_moving(self):
        self.assertEqual(simulate_calls(PeriodicCallback(None, 5000), [-1, -1, 0]), [1005, 1010, 1015])

    def test_a_backwards_step_right_after_an_overrun(self):
        self.assertEqual(simulate_calls(PeriodicCallback(None, 5000), [7, -2, 0]), [1005, 1015, 1020])

    def test_every_call_is_later_than_the_last_whatever_the_clock_does(self):
        times = simulate_calls(PeriodicCallback(None, 250), [-0.1, 0.3, -0.2, -0.05, 0, -0.3])
        self.assertTrue(all(times[i + 1] > times[i] for i in range(len(times) - 1)), times)
