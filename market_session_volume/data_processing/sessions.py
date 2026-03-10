"""Non-overlapping session-hour partitions (each hour 0-23 in exactly one bucket)."""

SESSION_HOURS = {
    "sydney": [22, 23, 0, 1, 2, 3, 4, 5, 6],
    "tokyo": [7, 8],
    "london": [9, 10, 11, 12],
    "london_new_york_overlap": [13, 14, 15, 16],
    "new_york": [17, 18, 19, 20, 21],
}
