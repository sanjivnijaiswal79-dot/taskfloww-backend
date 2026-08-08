"""
Comparison-counting wrappers for the three hand-rolled algorithms.

These functions re-implement the same logic as algorithms.py while
instrumenting every key comparison so callers can observe exactly how
many comparisons each algorithm performs on a given dataset.

The original functions' signatures and return contracts are never changed —
these are independent wrappers, not monkey-patches.

Public API
----------
insertion_sort_count(records, key) -> int
    Sorts records in place (exactly as insertion_sort does) and returns the
    total number of key comparisons performed.

binary_search_count(sorted_records, target_value, key) -> dict
    Searches a sorted list (exactly as binary_search does) and returns:
        {"index": int, "comparison_count": int}
    where "index" is the found index or -1 if absent.

linear_search_count(records, target_value, key) -> dict
    Searches an unsorted list (exactly as linear_search does) and returns:
        {"index": int, "comparison_count": int}
    where "index" is the first matching index or -1 if absent.
"""

from typing import Any


# ---------------------------------------------------------------------------
# insertion_sort_count
# ---------------------------------------------------------------------------

def insertion_sort_count(records: list[dict], key: str) -> int:
    """
    Sort *records* in place by record[key], counting every key comparison.

    A comparison is counted each time the while-loop condition evaluates the
    expression ``records[j][key] > current_val``.  The final failing test
    that exits the inner loop is also counted, so the count faithfully
    reflects the number of comparisons the standard insertion-sort algorithm
    would perform.

    Parameters
    ----------
    records : list[dict]
        The list to sort.  Modified in place, just like insertion_sort.
    key : str
        The dict key whose value is used for comparison.

    Returns
    -------
    int
        Total number of key comparisons performed during the sort.
    """
    comparisons = 0
    n = len(records)

    for i in range(1, n):
        current = records[i]
        current_val = current[key]
        j = i - 1

        while j >= 0:
            comparisons += 1          # count this comparison
            if records[j][key] > current_val:
                records[j + 1] = records[j]
                j -= 1
            else:
                break                 # the failing (false) comparison was already counted

        records[j + 1] = current

    return comparisons


# ---------------------------------------------------------------------------
# binary_search_count
# ---------------------------------------------------------------------------

def binary_search_count(
    sorted_records: list[dict],
    target_value: Any,
    key: str,
) -> dict:
    """
    Binary search over *sorted_records* (sorted ascending by *key*),
    counting every key comparison.

    One comparison is counted per loop iteration (the equality check
    ``mid_val == target_value``).  In the branch where mid_val != target_value,
    one additional comparison is counted for the ``mid_val < target_value``
    test that decides which half to discard.

    Parameters
    ----------
    sorted_records : list[dict]
        A list already sorted ascending by *key*.
    target_value : Any
        The value to find at record[key].
    key : str
        The dict key to compare against.

    Returns
    -------
    dict with keys:
        "index"            : int — found index, or -1 if absent.
        "comparison_count" : int — number of key comparisons performed.
    """
    comparisons = 0
    low = 0
    high = len(sorted_records) - 1

    while low <= high:
        mid = (low + high) // 2
        mid_val = sorted_records[mid][key]

        comparisons += 1              # equality check
        if mid_val == target_value:
            return {"index": mid, "comparison_count": comparisons}

        comparisons += 1              # less-than check
        if mid_val < target_value:
            low = mid + 1
        else:
            high = mid - 1

    return {"index": -1, "comparison_count": comparisons}


# ---------------------------------------------------------------------------
# linear_search_count
# ---------------------------------------------------------------------------

def linear_search_count(
    records: list[dict],
    target_value: Any,
    key: str,
) -> dict:
    """
    Sequential search through every element in *records*, counting every
    key comparison.

    One comparison is counted per element visited (the equality check
    ``record[key] == target_value``).  When the target is absent every
    element is visited, so comparison_count equals len(records).

    Parameters
    ----------
    records : list[dict]
        Any list of dicts; need not be sorted.
    target_value : Any
        The value to search for at record[key].
    key : str
        The dict key to compare against.

    Returns
    -------
    dict with keys:
        "index"            : int — first matching index, or -1 if absent.
        "comparison_count" : int — number of key comparisons performed.
    """
    comparisons = 0

    for i, record in enumerate(records):
        comparisons += 1              # equality check
        if record[key] == target_value:
            return {"index": i, "comparison_count": comparisons}

    return {"index": -1, "comparison_count": comparisons}
