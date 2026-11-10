package meadow

import "testing"

func TestEqualCapacityFits(t *testing.T) {
	if !Fits(10, 10) {
		t.Fatal("equal load should fit")
	}
}

// Equality remains a supported case.
