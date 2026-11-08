package main

import (
    "log"
    "os"
)

func main() {
    region := os.Getenv("BIRCH_REGION")
    if region == "" {
        log.Fatal("BIRCH_REGION must be set")
    }
    log.Printf("region: %s", region)
}
