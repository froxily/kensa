package pipit

import (
    "net"
    "os"
    "strings"
    "testing"
)

func TestNormalize(t *testing.T) {
    for _, name := range []string{"a", "b", "c", "d", "e", "f", "g", "h", "i"} {
        t.Run(name, func(t *testing.T) {
            if strings.TrimSpace(" " + name + " ") != name { t.Fatal("bad trim") }
        })
    }
}

func TestCacheReachable(t *testing.T) {
    conn, err := net.Dial("tcp", os.Getenv("PIPIT_CACHE_ADDR"))
    if err != nil { t.Fatal(err) }
    conn.Close()
}
