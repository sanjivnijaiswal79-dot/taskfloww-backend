"""
Hand-rolled sorting and searching algorithms.

These functions are the real engine behind the GET /tasks and GET /tasks/search
endpoints — they operate on live data fetched from the tasks table and are
never replaced by Python's built-in sorted() or list.sort().

Public API
----------
insertion_sort(records, key)
    Sort a list of dicts in place by records[i][key].
    Mutates the list directly; no return value.

binary_search(sorted_records, target_value, key) -> int
    Binary search over a list already sorted by *key*.
    Returns the index of a matching record, or -1 if not found.

linear_search(records, target_value, key) -> int
    Linear (sequential) search — no sort required.
    Returns the index of the first matching record, or -1 if not found.
"""

from typing import Any


# ---------------------------------------------------------------------------
# insertion_sort
# ---------------------------------------------------------------------------

def insertion_sort(records: list[dict], key: str) -> None:
    """
    Sort *records* in place by the value at record[key].

    Algorithm
    ---------
    Starting from the second element (index 1), the algorithm maintains a
    sorted prefix on the left.  For each new element, it scans left, shifting
    elements one position to the right until it finds the correct insertion
    spot, then drops the element there.

    Complexity
    ----------
    Best case  : O(n)     — list already sorted; the inner while never shifts.
    Worst case : O(n²)    — list sorted in reverse; every element must travel
                            all the way to index 0.

    Parameters
    ----------
    records : list[dict]
        The list to sort.  Modified in place.
    key : str
        The dict key whose value is used for comparison.

    Returns
    -------
    None  (mutation only — the caller reads the list after the call).
    """
    n = len(records)
    for i in range(1, n):
        current = records[i]
        current_val = current[key]
        j = i - 1
        # Shift elements that are greater than current_val one position right
        while j >= 0 and records[j][key] > current_val:
            records[j + 1] = records[j]
            j -= 1
        # Place current element in its correct sorted position
        records[j + 1] = current


# ---------------------------------------------------------------------------
# binary_search
# ---------------------------------------------------------------------------

def binary_search(sorted_records: list[dict], target_value: Any, key: str) -> int:
    """
    Binary search over *sorted_records* (sorted ascending by *key*).

    The list must already be sorted by *key* — use insertion_sort first.

    Algorithm
    ---------
    Maintain low and high pointers that bracket the live search window.
    Compute mid = (low + high) // 2, compare sorted_records[mid][key] with
    target_value, and halve the window accordingly.

    Complexity
    ----------
    Best case  : O(1)      — target is at the first mid position computed.
    Worst case : O(log n)  — target is absent or at a leaf of the halving tree.

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
    int
        Index of a record where record[key] == target_value, or -1 if absent.
        When duplicates exist the returned index is not guaranteed to be the
        first occurrence — use linear_search if you need the first match.
    """
    low = 0
    high = len(sorted_records) - 1

    while low <= high:
        mid = (low + high) // 2
        mid_val = sorted_records[mid][key]

        if mid_val == target_value:
            return mid
        elif mid_val < target_value:
            low = mid + 1
        else:
            high = mid - 1

    return -1


# ---------------------------------------------------------------------------
# linear_search
# ---------------------------------------------------------------------------

def linear_search(records: list[dict], target_value: Any, key: str) -> int:
    """
    Sequential search through every element in *records*.

    No pre-sorting required.  Returns the index of the *first* record whose
    record[key] == target_value.

    Complexity
    ----------
    Best case  : O(1)  — match found at index 0.
    Worst case : O(n)  — target is at the last position or absent entirely.

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
    int
        Index of the first matching record, or -1 if no match exists.
    """
    for i, record in enumerate(records):
        if record[key] == target_value:
            return i
    return -1
