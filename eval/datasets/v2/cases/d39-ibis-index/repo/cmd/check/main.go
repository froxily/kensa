package main

import (
    "bufio"
    "fmt"
    "net"
    "os"
    "strings"
)

func main() {
    conn, err := net.Dial("tcp", "127.0.0.1:6379")
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    defer conn.Close()
    reader := bufio.NewReader(conn)
    for i := 1; i <= 20; i++ {
        fmt.Fprint(conn, "PING\r\n")
        reply, err := reader.ReadString('\n')
        if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
        fmt.Printf("cache ping %d: %s\n", i, strings.TrimSpace(reply))
    }
    fmt.Fprintf(conn, "SELECT %s\r\n", os.Getenv("IBIS_CACHE_DB"))
    reply, err := reader.ReadString('\n')
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    if strings.HasPrefix(reply, "-") {
        fmt.Fprintln(os.Stderr, "Redis:", strings.TrimSpace(reply))
        os.Exit(1)
    }
}
