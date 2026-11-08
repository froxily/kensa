package main

import (
    "bytes"
    "fmt"
    "io"
    "net/http"
    "os"
)

func main() {
    repo := os.Getenv("GITHUB_REPOSITORY")
    token := os.Getenv("JUNCO_REVIEW_TOKEN")
    client := &http.Client{}
    base := "https://api.github.com/repos/" + repo + "/pulls/17"
    for page := 1; page <= 20; page++ {
        req, _ := http.NewRequest("GET", fmt.Sprintf("%s/files?per_page=1&page=%d", base, page), nil)
        req.Header.Set("Authorization", "Bearer " + token)
        req.Header.Set("Accept", "application/vnd.github+json")
        resp, err := client.Do(req)
        if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
        io.Copy(io.Discard, resp.Body)
        resp.Body.Close()
        fmt.Printf("read file page %d: HTTP %d\n", page, resp.StatusCode)
        if resp.StatusCode != 200 { os.Exit(1) }
    }
    payload, err := os.ReadFile("data/review-payload.json")
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    req, _ := http.NewRequest("POST", base + "/reviews", bytes.NewReader(payload))
    req.Header.Set("Authorization", "Bearer " + token)
    req.Header.Set("Accept", "application/vnd.github+json")
    req.Header.Set("Content-Type", "application/json")
    resp, err := client.Do(req)
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    defer resp.Body.Close()
    body, _ := io.ReadAll(resp.Body)
    fmt.Fprintf(os.Stderr, "review request: HTTP %d\n%s\n", resp.StatusCode, body)
    if resp.StatusCode >= 300 { os.Exit(1) }
}
