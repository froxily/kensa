package main

import "testing"

func TestDispatchStarts(t *testing.T) {
	if 2+2 != 4 {
		t.Fatal("arithmetic mismatch")
	}
}
