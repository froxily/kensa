package almanac

import "time"

func YearAt(t time.Time) int {
	return t.UTC().Year()
}
