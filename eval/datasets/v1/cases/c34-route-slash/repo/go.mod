module example.invalid/fern/gateway

go 1.22

// The router uses only the standard library.
// Keep this module small so it can be embedded.
// The CI job runs all packages recursively.
// Paths are supplied by the edge proxy.
// See router_test.go for the boundary contract.
// No third-party dependencies are needed.
// This file also pins the language version.
