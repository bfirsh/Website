
from __future__ import absolute_import
import unittest

from hypothesis import given
from hypothesis.strategies import lists, integers

from apps.majority_judgement import (
    get_floor_median, calculate_score, calculate_normalised_score,
    calculate_max_normalised_score,
    MajorityJudgementException
)


# TODO throw hypothesis tests at this, then sob
class CFPRankingTestCase(unittest.TestCase):
    def test_get_floor_median(self):
        assert get_floor_median([1]) == 1
        assert get_floor_median([1, 2]) == 1
        assert get_floor_median([1, 2, 3]) == 2
        assert get_floor_median([1, 2, 3, 4]) == 2
        assert get_floor_median([1, 2, 3, 4, 5]) == 3

    def test_calculate_score(self):
        score_set = [0, 0]
        assert calculate_score(score_set) == 0
        # Check it's non-destructive
        assert score_set == [0, 0]

        assert calculate_score([0, 1]) == 1
        # Check that it's sort-agnostic
        assert calculate_score([0, 1]) == calculate_score([1, 0])
        assert calculate_score([2, 2]) == 8

        # Because we take the median value out each time this is calculated
        # as 2 * 9 + 2 * 1
        assert calculate_score([2, 2, 0]) == 20
        assert calculate_score([2, 1, 2, 0]) == 47

        # Check different bases work
        assert calculate_score([0, 1], 2) == 1
        assert calculate_score([0, 3], 4) == 3
        assert calculate_score([1, 0, 3], 4) == 19

        # Votes outside of the range [0, base) should fail (i.e. 0<= v < 3)
        with self.assertRaises(MajorityJudgementException):
            calculate_score([3])

        with self.assertRaises(MajorityJudgementException):
            calculate_score([-1])

    def test_calculate_normalised_score(self):
        # Basic tests
        assert calculate_normalised_score([1], 1) == 1
        assert calculate_normalised_score([1], 2) == 4

        expected = calculate_score([2, 2, 1])
        assert calculate_normalised_score([2, 2], 3) == expected

        expected = calculate_score([2, 2, 0])
        assert calculate_normalised_score([2, 2], 3, default_vote=0) == expected

        # Basic length checks
        with self.assertRaises(MajorityJudgementException):
            calculate_normalised_score([2, 2], 1)

        # Fail fast if default vote is out of bounds
        with self.assertRaises(MajorityJudgementException):
            calculate_normalised_score([2, 2], 1, default_vote=3)

        with self.assertRaises(MajorityJudgementException):
            calculate_normalised_score([2, 2], 1, default_vote=-1)

    def test_calculate_max_normalised_score(self):
        def assert_within_delta(test, expected):
            result = calculate_max_normalised_score(test)
            assert -0.01 < result - expected < 0.01

        assert calculate_max_normalised_score([]) == 0
        assert_within_delta([0, ], 0.0)
        assert_within_delta([2, ], 1.0)

        assert_within_delta([0, 1], 0.125)
        assert_within_delta([2, 1], 0.625)
        assert_within_delta([2, 2, 1], 0.885)
        assert_within_delta([1, 2, 2, 1], 0.625)

    def test_ordering(self):
        expected = [[2, 1], [1, 2, 2, 0], [1, 1], [2, 1, 0], [0, 2, 0]]
        test = [[0, 2, 0], [1, 2, 2, 0], [2, 1, 0], [2, 1], [1, 1]]

        # Sort test using the max normalised score
        result = sorted(test, key=lambda x: calculate_max_normalised_score(x),
                        reverse=True)

        assert expected == result

    @given(lists(integers(min_value=0, max_value=2)))
    def test_score_rankings_increase_as_expected(self, test_scores):
        initial = calculate_max_normalised_score(test_scores)
        increased = test_scores + [2, ]
        assert len(increased) > len(test_scores)

        increased = calculate_max_normalised_score(increased)
        assert initial <= increased

    @given(lists(integers(min_value=0, max_value=2)))
    def test_score_rankings_decrease_as_expected(self, test_scores):
        initial = calculate_max_normalised_score(test_scores)
        decreased = test_scores + [0, ]
        assert len(decreased) > len(test_scores)

        decreased = calculate_max_normalised_score(decreased)
        assert initial >= decreased
