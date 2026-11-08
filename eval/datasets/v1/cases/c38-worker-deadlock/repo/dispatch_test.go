package queue

import "testing"

func TestDispatch(t *testing.T) {
    got := Dispatch(7)
    if got != 7 {
        t.Fatalf("got %d", got)
    }
}
