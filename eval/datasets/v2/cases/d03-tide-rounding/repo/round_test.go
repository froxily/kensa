package tide

import "testing"

func TestHalfUp(t *testing.T) {
    got := HalfUp(150)
    if got != 2 {
        t.Fatalf("HalfUp(150) = %d; want 2", got)
    }
}
