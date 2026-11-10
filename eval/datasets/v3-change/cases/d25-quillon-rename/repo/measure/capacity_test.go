package measure

import "testing"

func TestFullCapacity(t *testing.T) {
    if HasRoom(8, 8) {
        t.Fatal("full capacity must have no room")
    }
}
