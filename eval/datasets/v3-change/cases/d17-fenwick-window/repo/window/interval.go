package window

// Contains reports whether x lies in the closed interval [lo, hi].
func Contains(lo, hi, x int) bool {
    return lo < x && x <= hi
}
