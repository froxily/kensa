package messages

import "testing"

func TestIdentityMessages(t *testing.T) {
    for _, value := range []string{"a", "b", "c", "d", "e", "f", "g", "h"} {
        t.Run(value, func(t *testing.T) {
            if got := ErrorMessage(value); got != value { t.Fatalf("got %q", got) }
        })
    }
}

func TestOfflineMessage(t *testing.T) {
    got := ErrorMessage("offline")
    want := "database connection refused"
    if got != want { t.Fatalf("ErrorMessage(offline) = %q; want %q", got, want) }
}
