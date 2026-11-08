package main

import (
    "fmt"
    "net/http"
    "os"
    "strings"
    "time"
)

func main() {
    address, err := os.ReadFile("settings/nigella-health.txt")
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    client := http.Client{Timeout: time.Second}
    for attempt := 1; attempt <= 20; attempt++ {
        response, err := client.Get(strings.TrimSpace(string(address)))
        if err == nil { response.Body.Close(); fmt.Println("health status:", response.Status); return }
        fmt.Fprintf(os.Stderr, "health attempt %02d: %v\n", attempt, err)
        time.Sleep(100 * time.Millisecond)
    }
    os.Exit(1)
}
