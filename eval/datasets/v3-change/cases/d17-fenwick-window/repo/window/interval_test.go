package window

import "testing"

func TestContainsLowerEdge(t *testing.T) {
    if !Contains(4, 9, 4) {
        t.Fatal("lower edge should be included")
    }
}

func TestContainsOutside(t *testing.T) {
    if Contains(4, 9, 10) {
        t.Fatal("value above upper edge should be excluded")
    }
}
