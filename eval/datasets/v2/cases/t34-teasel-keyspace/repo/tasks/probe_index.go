package main

import (
    "bufio"
    "fmt"
    "os"
    "os/exec"
)

func main() {
    f, err := os.Open("tasks/index-segments.txt")
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    defer f.Close()
    scanner := bufio.NewScanner(f)
    for scanner.Scan() { fmt.Println("indexed segment:", scanner.Text()) }
    if err := scanner.Err(); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    output, err := exec.Command("cqlsh", "127.0.0.1", "19042", "-e", "USE scans;").CombinedOutput()
    fmt.Print(string(output))
    if err != nil { fmt.Fprintln(os.Stderr, "index probe failed"); os.Exit(1) }
}
