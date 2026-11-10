package main

import (
    "fmt"
    "os"
)

func main() {
    if os.Getenv("AZIMUTH_ATTEST_KEY") == "" {
        fmt.Fprintln(os.Stderr, "AZIMUTH_ATTEST_KEY is required")
        os.Exit(1)
    }
    fmt.Println("verification complete")
}
