package config

import (
    "fmt"
    "os"
)

func Region() (string, error) {
    value := os.Getenv("SERVICE_REGION")
    if value == "" {
        return "", fmt.Errorf("SERVICE_REGION must be set")
    }
    return value, nil
}
