package gateway

import "testing"

func TestNormalizeRoot(t *testing.T) {
    if got := Normalize("/"); got != "/" {
        t.Fatalf("root route: got %q, want /", got)
    }
}
func TestNormalizeNested(t *testing.T) {
    if got := Normalize("/shop/"); got != "/shop" { t.Fatal(got) }
}
