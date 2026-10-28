"""Tests for step_guard: SystemExit from a library must not end a harvest quietly.

Run with: python3 -m unittest test_step_guard
"""

import unittest

from step_guard import StepEnded, check_no_dimensions, run_step


class RunStepTests(unittest.TestCase):
    def test_returns_what_the_step_returns(self):
        self.assertEqual(run_step("Dimensions", lambda a, b=2: (a, b), 1, b=3), (1, 3))

    def test_arguments_are_passed_through(self):
        seen = []
        run_step("x", lambda *a, **k: seen.append((a, k)), 1, 2, k=3)
        self.assertEqual(seen, [((1, 2), {"k": 3})])

    def test_system_exit_becomes_an_ordinary_exception(self):
        for code in (0, 1, 2, None, "dsl.ini not found"):
            def step():
                raise SystemExit(code)

            with self.assertRaises(StepEnded, msg=repr(code)) as cm:
                run_step("Dimensions login", step)
            self.assertIsInstance(cm.exception, Exception)
            self.assertIn("Dimensions login", str(cm.exception))

    def test_even_exit_zero_is_an_error(self):
        # dimcli exits 0 on a missing credentials file; that is what hid it
        def step():
            raise SystemExit(0)

        with self.assertRaises(StepEnded):
            run_step("Dimensions", step)

    def test_the_exit_code_or_message_is_in_the_text(self):
        def exit_two():
            raise SystemExit(2)

        def exit_text():
            raise SystemExit("credentials missing")

        with self.assertRaises(StepEnded) as cm:
            run_step("s", exit_two)
        self.assertIn("2", str(cm.exception))
        with self.assertRaises(StepEnded) as cm:
            run_step("s", exit_text)
        self.assertIn("credentials missing", str(cm.exception))

    def test_ordinary_exceptions_pass_through_unchanged(self):
        err = ValueError("bad")

        def step():
            raise err

        with self.assertRaises(ValueError) as cm:
            run_step("s", step)
        self.assertIs(cm.exception, err)

    def test_keyboard_interrupt_is_not_swallowed(self):
        def step():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_step("s", step)

    def test_a_step_that_ended_is_not_confused_with_one_that_returned_none(self):
        self.assertIsNone(run_step("s", lambda: None))


class NoDimensionsTests(unittest.TestCase):
    def test_allowed_for_a_test_target(self):
        check_no_dimensions(True, production=False)  # no error

    def test_not_asking_is_always_fine(self):
        check_no_dimensions(False, production=True)
        check_no_dimensions(False, production=False)

    def test_refused_for_production(self):
        with self.assertRaises(ValueError) as cm:
            check_no_dimensions(True, production=True)
        self.assertIn("-no-dimensions", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
