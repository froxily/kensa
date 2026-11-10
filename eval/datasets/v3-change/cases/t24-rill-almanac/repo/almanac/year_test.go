package almanac

import (
	"testing"
	"time"
)

func TestCurrentCalendarYear(t *testing.T) {
	if got := YearAt(time.Now()); got != 2025 {
		t.Errorf("current year = %d, want 2025", got)
	}
}
