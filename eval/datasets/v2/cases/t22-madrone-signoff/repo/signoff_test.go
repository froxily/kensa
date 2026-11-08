package signoff

import (
    "os"
    "strings"
    "testing"
)

func TestLabels(t *testing.T) {
    for _, label := range []string{"acorn", "bloom", "crown", "drift", "elmwood", "frond", "grove", "hedge", "islet", "jade"} {
        t.Run(label, func(t *testing.T) {
            if strings.TrimSpace(label) == "" { t.Fatal("empty label") }
        })
    }
}

func TestSignoff(t *testing.T) {
    if os.Getenv("MADRONE_SIGNOFF") == "" {
        t.Fatal("MADRONE_SIGNOFF must be set")
    }
}
