package gateway

import "strings"

// Normalize removes trailing separators from a route.
func Normalize(path string) string {
    if path == "" {
        return "/"
    }
    return strings.TrimRight(path, "/")
}
