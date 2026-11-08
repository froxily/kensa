package capacity

import "testing"

func TestZeroWidth(t *testing.T) { if Liters(0, 4, 7) != 0 { t.Fatal("width") } }
func TestZeroHeight(t *testing.T) { if Liters(4, 0, 7) != 0 { t.Fatal("height") } }
func TestZeroDepth(t *testing.T) { if Liters(4, 7, 0) != 0 { t.Fatal("depth") } }
func TestEmptyBox(t *testing.T) { if Liters(0, 0, 0) != 0 { t.Fatal("empty") } }
func TestFlatBox(t *testing.T) { if Liters(6, 0, 9) != 0 { t.Fatal("flat") } }
func TestCubeInLiters(t *testing.T) {
    got := Liters(10, 10, 10)
    if got != 1 { t.Fatalf("Liters(10,10,10) = %g; want 1", got) }
}
